"""Telegram via shared ADB. No network client or account credentials."""
from .diagnostics import record, logged, step
import asyncio
import hashlib
from contextlib import asynccontextmanager
from .adb import AndroidBridge
from .domain import SendRejected, ForegroundDeferred
from .domain import Message, LayoutError, nodes, unique, center, input_command, tail_delta
from .anon_xml import box
from .telegram_xml import dialog_name, label, login_screen, records, local_search_candidates, opaque_dialog_rows
from .ui_wait import read_until


class Telegram:
    def __init__(self,settings,ingest,status,bridge=None):
        self.settings,self.ingest,self.status=settings,ingest,status
        self.bridge=bridge or AndroidBridge(settings)
        self.selectors=settings.telegram_selectors
        self.package=self.selectors.get('package','org.telegram.messenger')
        self.poll_task=None
        self.blocked=False
        self.pending_send=None
        self.histories={}
        self.messages={}
        self.titles={}
        self.sequence=0
        self.cursor=0
        self.last_chat_rotation=0.0
        self.lifecycle=None
        self.quarantined=set()
        self.discovery_pending=False
        self.discovery_cursor=0
        self.discovery_private=False

    @logged('telegram.connect')
    async def connect(self):
        if not all(self.selectors.get(k) for k in ('identity','chat_list','chat_rows','input','send','incoming','outgoing')):
            raise ValueError('Configure the Telegram XML selectors in settings.json.')
        if self.poll_task and not self.poll_task.done():
            return
        await self.bridge.connect()
        async with self.bridge.session(self.package):
            root=await self.dump()
            self.check_login(root)
            if nodes(root,self.selectors['input']):await self.process(root)
            else:
                for title,_ in self.rows(root):
                    key=self.key_for(title);self.titles[key]=title
                    await self.ingest(key,title,None,False)
                if not self.rows(root):
                    self.discovery_pending=bool(opaque_dialog_rows(root,self.package))
                    if self.discovery_pending:await self.discover_once(root)
                    else:self.status('Telegram list is not readable yet. Waiting for accessibility events; notifications will also discover conversations.')
        self.bridge.watch(self.package)
        self.poll_task=asyncio.create_task(self.poll())
        self.status('Telegram connected through ADB.')

    def check_login(self,root):
        if login_screen(root):
            raise ValueError('Sign in manually inside Telegram, then Connect Telegram (ADB).')

    async def dump(self):
        return await self.bridge.dump(self.package)

    async def tap(self,node):
        x,y=center(node)
        await self.bridge.shell(f'input tap {x} {y}')

    async def tap_send(self,root):
        target=unique(root,self.selectors['send'],'Telegram Send button')
        entry=unique(root,self.selectors['input'],'Telegram input')
        left,top,right,bottom=box(target)
        ex1,ey1,ex2,ey2=box(entry)
        # Telegram's accessible Send view includes part of the text editor.
        # Use only its exposed right-hand region, never the overlapping editor.
        if top<ey2 and bottom>ey1 and left<ex2 and right>ex1:
            left=max(left,ex2)
        if right<=left or bottom<=top:
            raise LayoutError('Send button has no unambiguous exposed XML bounds.')
        await self.bridge.shell(f'input tap {(left+right)//2} {(top+bottom)//2}')

    def identity(self,root):
        self.check_login(root)
        return unique(root,self.selectors['identity'],'Telegram conversation title').get('text','').strip()

    def key_for(self,title):
        return 'telegram:'+hashlib.sha256(title.encode('utf-8')).hexdigest()[:24]

    def rows(self,root):
        rows=nodes(root,self.selectors['chat_rows'])
        names=[dialog_name(n) for n in rows]
        # Never choose arbitrarily between equal display names.
        return [(name,n) for name,n in zip(names,rows) if name and names.count(name)==1]

    async def quarantine(self,key,reason):
        first=key not in self.quarantined
        self.quarantined.add(key)
        if first:
            if self.lifecycle:
                await self.lifecycle(key,'identity_unverified')
            self.status('Telegram identity needs verification: '+reason+
                ' Open the original conversation at its latest messages, then resume it after verification.')

    async def validate_target(self,root,key,baseline=None,allow_restore=False):
        """A matching title alone cannot replace evidence from the known transcript."""
        if key in self.quarantined and not allow_restore:
            raise LayoutError('Telegram identity remains unverified; no operation was submitted.')
        expected=self.titles.get(key)
        if expected is None:
            raise LayoutError('Telegram conversation is unknown; read it before sending.')
        try:
            title=self.identity(root)
        except ValueError:
            await self.quarantine(key,'The conversation header is not readable.')
            raise
        if title!=expected:
            await self.quarantine(key,'The recipient changed.')
            raise LayoutError('Telegram recipient changed; operation cancelled.')
        current=[(r[2],r[3],r[4]) for r in records(root,self.selectors)]
        previous=self.histories.get(key,[]) if baseline is None else baseline
        try:
            tail_delta(previous,current)
        except LayoutError:
            await self.quarantine(key,'This history does not overlap the original conversation.')
            raise LayoutError('Telegram history cannot verify this recipient; operation cancelled.')
        if allow_restore and key in self.quarantined:
            self.quarantined.remove(key)
            self.status('Telegram original history verified. The chat remains paused until Resume selected.')
        return current

    async def process(self,root):
        title=self.identity(root)
        if not title:
            raise LayoutError('Telegram conversation title is empty.')
        if title=='Telegram':raise LayoutError('Telegram system/account-code conversations are not automated.')
        key=self.key_for(title)
        self.titles[key]=title
        first=key not in self.histories
        previous=self.histories.get(key,[])
        try:
            current=await self.validate_target(root,key,allow_restore=True)
            delta=tail_delta(previous,current)
        except LayoutError:
            # Keep the original evidence. Replacing it would bless a same-name stranger.
            return key
        known=self.messages.setdefault(key,[])
        self.histories[key]=current
        for role,text,stamp in delta:
            self.sequence+=1
            message=Message(str(self.sequence),role,text)
            known.append((message,stamp))
            await self.ingest(key,title,message,not first and role=='user')
        await self.ingest(key,title,None,False)
        return key

    async def list_root(self,root):
        self.check_login(root)
        if nodes(root,self.selectors['input']):
            # Preserve drafts, including an uncertain send, instead of hiding them.
            entry=unique(root,self.selectors['input'],'Telegram input')
            if entry.get('text','').strip() not in ('',self.selectors.get('input_placeholder','Message')):
                raise ValueError('Telegram has an unsent draft. Clear it in Android before scanning chats.')
            await self.tap(unique(root,self.selectors['back'],'Telegram back button'))
            root=await read_until(self.dump,lambda r:bool(nodes(r,self.selectors['chat_list'])),
                                 'opening the Telegram chat list',self.settings.accessibility_enabled)
        self.check_login(root)
        if not nodes(root,self.selectors['chat_list']):
            raise LayoutError('Open the Telegram chat list in Android. No supported chat list was found.')
        return root

    async def discover_once(self,root):
        """Read one visible private row per transaction; never infer its identity from its position."""
        if nodes(root,self.selectors['input']):root=await self.list_root(root)
        if not self.discovery_private:
            private=[n for n in root.iter('node') if n.get('package')==self.package
                     and label(n).split('\n')[0]=='Private']
            if len(private)!=1:
                self.discovery_pending=False
                raise LayoutError('Telegram private-chat filter is not uniquely exposed.')
            await self.tap(private[0]);root=await self.dump()
            self.discovery_private=True
        rows=opaque_dialog_rows(root,self.package)
        if self.discovery_cursor>=min(len(rows),20):
            self.discovery_pending=False
            return
        target=rows[self.discovery_cursor];self.discovery_cursor+=1
        await self.tap(target)
        opened=await read_until(self.dump,lambda r:len(nodes(r,self.selectors['identity']))==1 and len(nodes(r,self.selectors['input']))==1,
                                'opening a Telegram conversation',self.settings.accessibility_enabled)
        # An actual private conversation needs a composer, a unique header and
        # no group/channel/bot header status. Row text is not an identity source.
        headers=nodes(opened,self.selectors['identity'])
        inputs=nodes(opened,self.selectors['input'])
        if len(headers)==1 and len(inputs)==1:
            import re
            header_bottom=box(inputs[0])[1]
            statuses=[label(n) for n in opened.iter('node') if box(n)[1]<min(header_bottom,160)]
            if self.identity(opened)!='Telegram' and not any(re.search(r'\b\d+ (members|subscribers)\b|^bot$',t,re.I) for t in statuses):
                await self.process(opened)
            await self.list_root(opened)
        else:
            self.discovery_pending=False
            raise LayoutError('Telegram row did not expose a supported private conversation; discovery paused.')
        if self.discovery_cursor>=min(len(rows),20):self.discovery_pending=False

    async def search_local(self,root,title):
        command=input_command(title)
        self.check_login(root)
        if nodes(root,self.selectors['input']):
            if self.identity(root).casefold()==title.casefold():
                return root
            entry=unique(root,self.selectors['input'],'Telegram input')
            if entry.get('text','').strip() not in ('',self.selectors.get('input_placeholder','Message')):
                raise ValueError('Telegram has an unsent draft; switching conversations is paused.')
            await self.tap(unique(root,self.selectors['back'],'Telegram back button'))
            root=await self.dump()
        search=unique(root,{'package':self.package,'class':'android.widget.EditText','content-desc':'Search Chats'},'local chat search')
        toolbar=[n for n in root.iter('node') if n.get('package')==self.package and n.get('content-desc')=='More options']
        if toolbar and box(search)[1]<max(box(n)[3] for n in toolbar):
            scrolls=[n for n in root.iter('node') if n.get('package')==self.package and n.get('scrollable')=='true'
                     and box(n)[3]-box(n)[1]>(box(n)[2]-box(n)[0])*.7]
            if len(scrolls)!=1:
                raise ValueError('Expand the Telegram search bar before opening this chat.')
            x1,y1,x2,y2=box(scrolls[0]);x=(x1+x2)//2
            await self.bridge.shell(f'input swipe {x} {y1+(y2-y1)//3} {x} {y1+2*(y2-y1)//3} 400')
            root=await self.dump()
            search=unique(root,{'package':self.package,'class':'android.widget.EditText','content-desc':'Search Chats'},'local chat search')
            if box(search)[1]<max(box(n)[3] for n in toolbar):
                raise ValueError('Telegram search bar is covered by the toolbar; navigation paused.')
        await self.tap(search)
        root=await self.dump()
        search=unique(root,{'package':self.package,'class':'android.widget.EditText','content-desc':'Search Chats'},'local chat search')
        if search.get('focused')=='false':
            raise ValueError('Telegram search did not receive focus; nothing was typed.')
        old=search.get('text','')
        if old not in ('','Search Chats',title):
            if len(old)>100:
                raise ValueError('Clear the existing Telegram search manually.')
            await self.bridge.shell('input keyevent 123 '+' '.join(['67']*len(old)))
            root=await self.dump()
            search=unique(root,{'package':self.package,'class':'android.widget.EditText','content-desc':'Search Chats'},'local chat search')
            if search.get('text') not in ('','Search Chats'):
                raise ValueError('Could not clear the Telegram search safely.')
        if old!=title:
            await self.bridge.shell(command)
        for attempt in range(3):
            root=await self.dump()
            query=unique(root,{'package':self.package,'class':'android.widget.EditText','content-desc':'Search Chats'},'local chat search')
            if query.get('text')!=title:
                raise ValueError('Telegram search query did not match the requested chat.')
            matches=local_search_candidates(root,title,self.package)
            if len(matches)>1:
                raise ValueError('Multiple local chats have this name. Give them distinct names before using Rad.ai.')
            if len(matches)==1:
                await self.tap(matches[0])
                root=await self.dump()
                if self.identity(root).casefold()!=title.casefold():
                    raise ValueError('Telegram opened a different conversation; no message was sent.')
                return root
            if attempt<2:
                await asyncio.sleep(.3)
        raise ValueError('No unique existing local chat found. Global search results are not used.')

    @logged('telegram.open_existing')
    async def open_existing(self,title):
        title=title.strip()
        if not title or len(title)>80:
            raise ValueError('Enter an existing local chat name of 1-80 characters.')
        async with self.bridge.session(self.package):
            root=await self.search_local(await self.dump(),title)
            return await self.process(root)

    async def open_chat(self,root,key):
        if key in self.quarantined:
            raise LayoutError('Telegram identity remains unverified; open the original chat manually.')
        expected=self.titles.get(key)
        if expected is None:
            raise ValueError('Telegram conversation is no longer known; reconnect and scan the list.')
        if nodes(root,self.selectors['input']) and self.identity(root)==expected:
            await self.validate_target(root,key)
            return root
        if not self.selectors.get("scan_chat_list",True):
            root=await self.search_local(root,expected)
            await self.validate_target(root,key)
            return root
        root=await self.list_root(root)
        candidates=[n for name,n in self.rows(root) if name==expected]
        if len(candidates)!=1:
            raise ValueError('The selected Telegram chat is absent or ambiguous in the visible chat list.')
        await self.tap(candidates[0])
        root=await self.dump()
        if self.identity(root)!=expected:
            raise ValueError('Telegram opened a different conversation; operation cancelled.')
        await self.validate_target(root,key)
        return root

    @asynccontextmanager
    async def polling_session(self,scheduled):
        if scheduled:
            async with self.bridge.poll_session(self.package) as allowed:
                yield allowed
        else:
            async with self.bridge.session(self.package):
                yield True

    @logged('telegram.poll_once')
    async def poll_once(self,scheduled=False):
        async with self.polling_session(scheduled) as allowed:
            if not allowed:
                return
            root=await self.dump()
            self.check_login(root)
            if self.settings.accessibility_enabled:
                # Reading must never turn into periodic navigation. New background
                # messages are routed through the notification inbox instead.
                if nodes(root,self.selectors['input']):
                    self.discovery_pending=False
                    await self.process(root)
                elif self.discovery_pending and not self.blocked:
                    await self.discover_once(root)
                else:
                    for title,_ in self.rows(root):
                        if title=='Telegram':continue
                        key=self.key_for(title);self.titles[key]=title
                        await self.ingest(key,title,None,False)
                return
            if self.discovery_pending and not self.blocked:
                await self.discover_once(root)
                return
            if nodes(root,self.selectors['input']):
                key=await self.process(root)
                if self.blocked or key in self.quarantined:
                    return
                if not self.selectors.get("scan_chat_list",True):
                    now=self.bridge._clock()
                    if len(self.titles)>1 and now-self.last_chat_rotation>=self.settings.adb_focus_seconds:
                        self.last_chat_rotation=now
                        keys=list(self.titles)
                        current=self.key_for(self.identity(root))
                        target=keys[(keys.index(current)+1)%len(keys)]
                        root=await self.open_chat(root,target)
                        await self.process(root)
                    return
            if self.blocked:
                return
            if not self.selectors.get("scan_chat_list",True) and self.titles:
                root=await self.open_chat(root,next(iter(self.titles)))
                await self.process(root)
                return
            root=await self.list_root(root)
            rows=self.rows(root)
            if not rows:
                self.status('Telegram chat rows are not exposed by Android yet. This does not mean the account has no chats. Open an existing conversation or wait for a notification.')
                return
            for title,_ in rows:
                key=self.key_for(title)
                self.titles[key]=title
                await self.ingest(key,title,None,False)
            title,node=rows[self.cursor%len(rows)]
            self.cursor+=1
            await self.tap(node)
            root=await self.dump()
            if self.identity(root)!=title:
                raise LayoutError('Telegram row/title mismatch; no conversation text was imported.')
            await self.process(root)
            # Polling yields the shared device after one chat, not after the whole list.
            await self.list_root(root)

    async def poll(self):
        last_error=None
        while True:
            try:
                await self.poll_once(scheduled=True)
                last_error=None
            except asyncio.CancelledError:
                raise
            except Exception as error:
                record('telegram.poll',error,package=self.package,blocked=self.blocked)
                message='Telegram: '+str(error)
                if message!=last_error:
                    self.status(message)
                    last_error=message
            if self.bridge is not None:await self.bridge.wait_update(self.package)
            else:await asyncio.sleep(self.settings.adb_poll_seconds)

    @logged('telegram.message_menu')
    async def message_menu(self,root,key,message_id,action):
        await self.validate_target(root,key)
        pair=next((p for p in self.messages.get(key,[]) if p[0].id==message_id),None)
        if pair is None:
            raise ValueError('Selected Telegram message is no longer in the XML history.')
        message,stamp=pair
        matches=[r for r in records(root,self.selectors) if (r[2],r[3],r[4])==(message.role,message.text,stamp)]
        if len(matches)!=1:
            raise ValueError('Selected Telegram message is not uniquely visible.')
        x,y=center(matches[0][-1])
        await self.bridge.shell(f'input swipe {x} {y} {x} {y} 650')
        menu=await self.dump()
        await self.tap(unique(menu,self.selectors[action],f'Telegram {action} action'))
        return message

    @logged('telegram.send')
    async def send(self,key,text,reply_to=None):
        try:
            return await self._send(key,text,reply_to)
        except ForegroundDeferred:
            raise
        except Exception as error:
            if not self.blocked:
                raise SendRejected(str(error)) from error
            raise

    async def _send(self,key,text,reply_to=None):
        phase="validate_input"
        from .typing_draft import can_edit,write_reply
        if not text or len(text)>1500:raise ValueError('Reply must contain 1-1500 characters.')
        command=None if can_edit(self) else input_command(text)
        async with self.bridge.session(self.package):
            if self.blocked:
                raise ValueError('Inspect the uncertain Telegram operation before sending again.')
            root=await self.open_chat(await self.dump(),key)
            before=await self.validate_target(root,key)
            from .typing_draft import clear_waiting
            root=await clear_waiting(self,key,root)
            entry=unique(root,self.selectors['input'],'Telegram input')
            if entry.get('text','').strip() not in ('',self.selectors.get('input_placeholder','Message')):
                raise ValueError('Telegram input is not empty; clear the existing draft manually.')
            self.pending_send={"key":key,"text":text,"before":before,"submitted":False}
            try:
                if reply_to:
                    message=await self.message_menu(root,key,reply_to,'reply')
                    root=await self.dump()
                    await self.validate_target(root,key,baseline=before)
                    quotes=nodes(root,self.selectors.get('quote'))
                    if len(quotes)!=1 or message.text not in label(quotes[0]):
                        raise ValueError('Telegram reply preview could not be verified; inspect Android.')
                    entry=unique(root,self.selectors['input'],'Telegram input')
                phase="write_input"
                step("telegram.write_input",key=key,text_length=len(text))
                if command is None:await write_reply(self,root,text)
                else:
                    await self.tap(entry)
                    await self.bridge.shell(command)
                root=await read_until(self.dump,lambda r:any(n.get('text')==text for n in nodes(r,self.selectors['input'])),
                                     'updating the Telegram message input',self.settings.accessibility_enabled)
                await self.validate_target(root,key,baseline=before)
                if reply_to:
                    quotes=nodes(root,self.selectors.get('quote'))
                    if len(quotes)!=1 or message.text not in label(quotes[0]):
                        raise ValueError('Telegram reply preview changed after typing; inspect Android.')
                if unique(root,self.selectors['input'],'Telegram input').get('text')!=text:
                    raise ValueError('Telegram typed text or recipient changed; inspect the unsent draft.')
                phase="submit_send"
                self.pending_send["submitted"]=True
                step("telegram.submit_send",key=key,text_length=len(text))
                await self.tap_send(root)
                phase="verify_outgoing"
                step("telegram.verify_outgoing",key=key,text_length=len(text))
                for _ in range(4):
                    root=await self.dump()
                    after=await self.validate_target(root,key,baseline=before)
                    if any(role=='assistant' and body==text for role,body,_ in tail_delta(before,after)):
                        await self.process(root)
                        self.pending_send=None
                        return None
                    await asyncio.sleep(.25)
                raise ValueError('Telegram submission is unverified. Inspect Android; no automatic resend will occur.')
            except BaseException as error:
                self.blocked=True
                if isinstance(error,Exception) and not self.pending_send.get('submitted',False):
                    raise SendRejected(str(error)+' Message was not submitted. Inspect/clear the Android draft, then use Check send to resume safely.') from error
                raise

    @logged('telegram.reconcile')
    async def reconcile(self,key):
        pending=self.pending_send
        if not pending or pending['key']!=key:
            raise ValueError("No pending submission is available for this conversation.")
        async with self.bridge.session(self.package):
            root=await self.dump()
            after=await self.validate_target(root,key,baseline=pending['before'])
            matches=[r for r in tail_delta(pending['before'],after) if r[0]=='assistant' and r[1]==pending['text']]
            if not matches and pending.get('submitted') is False:
                entry=unique(root,self.selectors['input'],'Telegram input')
                if entry.get('text','').strip() not in ('',self.selectors.get('input_placeholder','Message')):
                    raise ValueError('Clear the unsent Android draft, then use Check send again. Nothing was submitted.')
                self.pending_send=None;self.blocked=False
                return False
            if len(matches)!=1:
                raise ValueError("Send remains unverified. Inspect Android; nothing was resent.")
            await self.process(root)
            self.pending_send=None
            self.blocked=False

    @logged('telegram.delete')
    async def delete(self,key,message):
        async with self.bridge.session(self.package):
            if self.blocked:
                raise ValueError('Inspect the uncertain Telegram operation first.')
            root=await self.open_chat(await self.dump(),key)
            if message.role!='assistant':
                raise ValueError('Only outgoing messages can be deleted.')
            before=await self.validate_target(root,key)
            pair=next((p for p in self.messages.get(key,[]) if p[0].id==message.id),None)
            if pair is None:
                raise ValueError('Selected Telegram message is no longer known.')
            deleted=(message.role,message.text,pair[1])
            remaining=list(before)
            if remaining.count(deleted)!=1:
                raise ValueError('Selected Telegram message is not uniquely visible.')
            remaining.remove(deleted)
            try:
                await self.message_menu(root,key,message.id,'delete')
                root=await self.dump()
                current=await self.validate_target(root,key,baseline=remaining)
                # Do not guess confirmation scope (for me / for everyone).
                if deleted in current:
                    raise ValueError('Complete the Telegram deletion confirmation in Android; deletion is not verified.')
                self.histories[key]=current
                self.messages[key]=[p for p in self.messages[key] if p[0].id!=message.id]
            except BaseException:
                self.blocked=True
                raise

    @asynccontextmanager
    async def typing(self,key):
        from .typing_draft import waiting_typing
        async with waiting_typing(self,key):yield

    async def close(self):
        self.bridge.unwatch(self.package)
        if self.poll_task:
            self.poll_task.cancel()
            await asyncio.gather(self.poll_task,return_exceptions=True)
            self.poll_task=None
