"""Telegram Android via shared ADB. No network client or account credentials."""
import asyncio
import hashlib
from contextlib import asynccontextmanager
from .adb import AndroidBridge
from .domain import Message, LayoutError, nodes, unique, center, input_command, tail_delta
from .telegram_xml import dialog_name, label, login_screen, records


class Telegram:
    def __init__(self,settings,ingest,status,bridge=None):
        self.settings,self.ingest,self.status=settings,ingest,status
        self.bridge=bridge or AndroidBridge(settings)
        self.selectors=settings.telegram_selectors
        self.package=self.selectors.get('package','org.telegram.messenger')
        self.poll_task=None
        self.blocked=False
        self.histories={}
        self.messages={}
        self.titles={}
        self.sequence=0
        self.cursor=0

    async def connect(self):
        if not all(self.selectors.get(k) for k in ('identity','chat_list','chat_rows','input','send','incoming','outgoing')):
            raise ValueError('Configure the Telegram XML selectors in settings.json.')
        if self.poll_task and not self.poll_task.done():
            return
        await self.bridge.connect()
        async with self.bridge.session(self.package):
            root=await self.dump()
            self.check_login(root)
        self.poll_task=asyncio.create_task(self.poll())
        self.status('Telegram Android connected through ADB.')

    def check_login(self,root):
        if login_screen(root):
            raise ValueError('Sign in manually inside Telegram Android, then Connect Telegram (ADB).')

    async def dump(self):
        return await self.bridge.dump(self.package)

    async def tap(self,node):
        x,y=center(node)
        await self.bridge.shell(f'input tap {x} {y}')

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

    async def process(self,root):
        title=self.identity(root)
        if not title:
            raise LayoutError('Telegram conversation title is empty.')
        key=self.key_for(title)
        self.titles[key]=title
        parsed=records(root,self.selectors)
        current=[(r[2],r[3],r[4]) for r in parsed]
        first=key not in self.histories
        previous=self.histories.get(key,[])
        try:
            delta=tail_delta(previous,current)
        except LayoutError:
            self.histories[key]=current
            self.messages[key]=[]
            self.status('Telegram history changed or scrolled; baseline refreshed without replaying old messages.')
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
            root=await self.dump()
        self.check_login(root)
        if not nodes(root,self.selectors['chat_list']):
            raise LayoutError('Open the Telegram chat list in Android. No supported chat list was found.')
        return root

    async def open_chat(self,root,key):
        expected=self.titles.get(key)
        if expected is None:
            raise ValueError('Telegram conversation is no longer known; reconnect and scan the list.')
        if nodes(root,self.selectors['input']) and self.identity(root)==expected:
            return root
        root=await self.list_root(root)
        candidates=[n for name,n in self.rows(root) if name==expected]
        if len(candidates)!=1:
            raise ValueError('The selected Telegram chat is absent or ambiguous in the visible chat list.')
        await self.tap(candidates[0])
        root=await self.dump()
        if self.identity(root)!=expected:
            raise ValueError('Telegram opened a different conversation; operation cancelled.')
        return root

    async def poll_once(self):
        async with self.bridge.session(self.package):
            root=await self.dump()
            self.check_login(root)
            if nodes(root,self.selectors['input']):
                await self.process(root)
            if self.blocked:
                return
            root=await self.list_root(root)
            rows=self.rows(root)
            if not rows:
                self.status('Telegram has no supported visible private chats. Open a conversation in Android.')
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
                await self.poll_once()
                last_error=None
            except asyncio.CancelledError:
                raise
            except Exception as error:
                message='Telegram Android: '+str(error)
                if message!=last_error:
                    self.status(message)
                    last_error=message
            await asyncio.sleep(self.settings.adb_poll_seconds)

    async def message_menu(self,root,key,message_id,action):
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

    async def send(self,key,text,reply_to=None):
        command=input_command(text)
        async with self.bridge.session(self.package):
            if self.blocked:
                raise ValueError('Inspect the uncertain Telegram operation before sending again.')
            root=await self.open_chat(await self.dump(),key)
            before=[(r[2],r[3],r[4]) for r in records(root,self.selectors)]
            entry=unique(root,self.selectors['input'],'Telegram input')
            if entry.get('text','').strip() not in ('',self.selectors.get('input_placeholder','Message')):
                raise ValueError('Telegram input is not empty; clear the existing draft manually.')
            try:
                if reply_to:
                    message=await self.message_menu(root,key,reply_to,'reply')
                    root=await self.dump()
                    quotes=nodes(root,self.selectors.get('quote'))
                    if len(quotes)!=1 or message.text not in label(quotes[0]):
                        raise ValueError('Telegram reply preview could not be verified; inspect Android.')
                    entry=unique(root,self.selectors['input'],'Telegram input')
                await self.tap(entry)
                await self.bridge.shell(command)
                root=await self.dump()
                if self.identity(root)!=self.titles[key] or unique(root,self.selectors['input'],'Telegram input').get('text')!=text:
                    raise ValueError('Telegram typed text or recipient changed; inspect the unsent draft.')
                await self.tap(unique(root,self.selectors['send'],'Telegram Send button'))
                for _ in range(4):
                    root=await self.dump()
                    if self.identity(root)!=self.titles[key]:
                        break
                    after=[(r[2],r[3],r[4]) for r in records(root,self.selectors)]
                    if any(role=='assistant' and body==text for role,body,_ in tail_delta(before,after)):
                        await self.process(root)
                        return None
                    await asyncio.sleep(.25)
                raise ValueError('Telegram submission is unverified. Inspect Android; no automatic resend will occur.')
            except BaseException:
                self.blocked=True
                raise

    async def delete(self,key,message):
        async with self.bridge.session(self.package):
            if self.blocked:
                raise ValueError('Inspect the uncertain Telegram operation first.')
            root=await self.open_chat(await self.dump(),key)
            if message.role!='assistant':
                raise ValueError('Only outgoing messages can be deleted.')
            try:
                await self.message_menu(root,key,message.id,'delete')
                root=await self.dump()
                # Do not guess confirmation scope (for me / for everyone).
                if self.identity(root)!=self.titles[key] or any(r[2]=='assistant' and r[3]==message.text for r in records(root,self.selectors)):
                    raise ValueError('Complete the Telegram deletion confirmation in Android; deletion is not verified.')
                self.histories[key]=[(r[2],r[3],r[4]) for r in records(root,self.selectors)]
                self.messages[key]=[p for p in self.messages[key] if p[0].id!=message.id]
            except BaseException:
                self.blocked=True
                raise

    @asynccontextmanager
    async def typing(self,key):
        # The GUI shows generation activity. No simulated Telegram network presence.
        yield

    async def close(self):
        if self.poll_task:
            self.poll_task.cancel()
            await asyncio.gather(self.poll_task,return_exceptions=True)
            self.poll_task=None
