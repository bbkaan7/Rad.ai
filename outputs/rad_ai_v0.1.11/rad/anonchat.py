"""ADB-only Android XML adapter. Windows cursor and desktop pixels are unused."""

import asyncio
import time
from contextlib import asynccontextmanager
from uuid import uuid4
from .adb import AndroidBridge
from .domain import SendRejected, ForegroundDeferred
from .domain import Message, LayoutError, xml_root, snapshot, unique, center, input_command, tail_delta, nodes


class AnonChat:
    def __init__(self, settings, ingest, status, new_chat, bridge=None):
        self.settings,self.ingest,self.status,self.new_chat=settings,ingest,status,new_chat
        self.bridge=bridge
        self.device=None
        self.lock=asyncio.Lock()
        self.poll_task=None
        self.key=None
        self.identity=None
        self.previous=[]
        self.sequence=0
        self.awaiting_match=False
        self.blocked=False
        self.pending_send=None
        self.identity_ambiguous=False
        self.view_left=False
        self.request_pending=False
        self.match_requested=False
        self.saw_gap=False
        self.auto_enabled=lambda:False
        self.lifecycle=None
        self.last_action=0
        self.visible_messages=[]
        self.retired=set()
        self.friend_keys={}
        self.bio_signature=None
        self.sessions={}
        self.friends=set()
        self.ready_to_leave=lambda key:True
        self.package=settings.selectors.get("package","io.anonchat")

    @asynccontextmanager
    async def session(self):
        if self.bridge is not None:
            async with self.bridge.session(self.settings.selectors["package"]):
                yield
        else:
            async with self.lock:
                yield

    @asynccontextmanager
    async def polling_session(self):
        if self.bridge is not None:
            async with self.bridge.poll_session(self.settings.selectors["package"]) as allowed:
                yield allowed
        else:
            async with self.lock:
                yield True

    async def shell(self,command):
        if self.bridge is not None:
            return await self.bridge.shell(command)
        if self.device is None:
            raise ValueError("ADB is not connected.")
        return await asyncio.to_thread(self.device.shell,command,timeout=10)

    async def dump(self):
        if self.bridge is not None:
            return await self.bridge.dump(self.settings.selectors["package"])
        # The command is fixed. Chat text can never become shell command syntax.
        result=await self.shell("uiautomator dump /sdcard/rad-ui.xml && cat /sdcard/rad-ui.xml")
        return xml_root(result)

    async def connect(self):
        if self.poll_task and not self.poll_task.done():
            if self.blocked:
                raise ValueError("Inspect the Android input and uncertain submission before restarting.")
            return
        s=self.settings
        if not all(s.selectors.get(key) for key in ("package","identity","incoming","outgoing")):
            raise ValueError("Configure AnonChat package, identity, incoming and outgoing XML selectors in settings.json.")
        if self.bridge is None:
            self.bridge=AndroidBridge(s)
        await self.bridge.connect()
        self.device=self.bridge.device
        # Reconnecting to the same Android view must not create a second person.
        # Existing keys and history are retained until a confirmed lifecycle boundary.
        self.bridge.watch(s.selectors["package"])
        self.poll_task=asyncio.create_task(self.poll())
        self.status("ADB connected. Waiting for readable AnonChat XML.")

    def system_labels(self,root):
        # Exclude entire bubble subtrees, including labels copied into accessibility wrappers.
        parents={c:p for p in root.iter() for c in p}
        excluded=set()
        for n in nodes(root,self.settings.selectors.get("incoming"))+nodes(root,self.settings.selectors.get("outgoing")):
            excluded.add(n)
            parent=parents.get(n)
            if parent is not None:
                excluded.update(parent.iter())
        return {(n.get("text") or n.get("content-desc","")).strip() for n in root.iter("node")
            if n not in excluded and n.get("package") in (None,self.package)}

    async def record(self,root,identity,first=False):
        if self.key in self.retired and self.key not in self.friends:return
        _,current=snapshot(root,self.settings.selectors)
        try:
            delta=tail_delta(self.previous,current)
        except LayoutError:
            self.previous=current
            self.identity_ambiguous=True
            if self.lifecycle:await self.lifecycle(self.key,"identity_unverified")
            self.status("AnonChat history cannot confirm this person. Replies paused; reconnect or start a verified new match.")
            return
        self.previous=current
        for role,text in delta:
            self.sequence+=1
            message=Message(str(self.sequence),role,text)
            self.visible_messages.append(message)
            await self.ingest(self.key,"AnonChat - "+identity,message,not first and role=="user")
        self.visible_messages=self.visible_messages[-200:]
        self.sessions[self.key]=(list(self.previous),list(self.visible_messages),self.bio_signature)
        await self.ingest(self.key,"AnonChat - "+identity,None,False)

    async def process(self,root,allow_actions=True):
        labels=self.system_labels(root)
        identities=nodes(root,self.settings.selectors.get("identity"))
        identity=identities[0].get("text","").strip() if len(identities)==1 else None
        home=not identity and bool(nodes(root,self.settings.selectors.get("search")))
        if not identity and not home:
            self.view_left=True
            return  # Friend-list previews and notifications cannot close the active chat.
        ended=bool(labels & {"Your partner ended chat","The partner ended chat","You ended chat",
            "Chat was ended by your partner","Your partner has ended the chat","Chat ended"})
        friendship=bool(labels & {"You and your partner became friends","The partner accepted your friend request",
            "Your partner accepted your friend request","The partner has accepted your friend request","You are now friends"})
        if (friendship or self.key in self.friends) and nodes(root,self.settings.selectors.get("input")):
            ended=False  # Old anonymous-close notices remain in a live friend history.
        bio=tuple(n.get("text") or n.get("content-desc","") for n in nodes(root,self.settings.selectors.get("bio")))
        # A hidden/scrolled-away bio is not evidence of a different partner.
        changed_bio=bool(bio and self.bio_signature and bio!=self.bio_signature)
        if identity:
            _,current=snapshot(root,self.settings.selectors)
            try:
                overlap=bool(self.previous and current)
                if overlap:tail_delta(self.previous,current)
            except LayoutError:
                overlap=False
            same_bio=bool(bio and self.bio_signature and bio==self.bio_signature)
            known_friend=self.friend_keys.get(identity)
            generic=self.identity in {"New partner","Partner"}
            staged=bool(self.key in self.friends and generic and not self.view_left and (same_bio or overlap))
            continuity=identity==self.identity and not changed_bio or (
                generic and not self.view_left and same_bio and (overlap or self.request_pending))
            promoted=bool(self.key and self.key not in self.retired and
                (friendship and continuity or staged) and known_friend in (None,self.key))
            if promoted:
                self.identity=identity
                if identity not in {"New partner","Partner"}:
                    self.friend_keys[identity]=self.key
            if self.awaiting_match and self.previous and not overlap and not ended and not friendship:
                # A confirmed Next action may skip the intermediate search screen.
                # A cleared/replaced transcript is then the observable match boundary.
                self.saw_gap=True
            waiting_old=self.awaiting_match and identity==self.identity and not self.saw_gap and not changed_bio
            if waiting_old and not ended and not friendship:
                return
            new=(self.key is None or (not promoted and identity!=self.identity) or
                (self.awaiting_match and self.saw_gap and not ended and not friendship) or
                (changed_bio and not overlap and not ended and not promoted))
            if new:
                if self.key and self.key not in self.friends and self.key not in self.retired:
                    self.retired.add(self.key)
                    if self.lifecycle:await self.lifecycle(self.key,"ended")
                opening=(self.awaiting_match or self.match_requested or self.key is None and not current) and not ended and not friendship
                self.key=self.friend_keys.get(identity) or "anonchat:"+uuid4().hex
                self.identity=identity
                self.identity_ambiguous=False
                if self.pending_send and self.pending_send["key"]!=self.key:
                    self.blocked=False
                    self.pending_send=None
                self.previous,self.visible_messages,self.bio_signature=self.sessions.get(self.key,([],[],None))
                self.retired.discard(self.key)
                self.awaiting_match=self.saw_gap=False
                self.request_pending=False
                self.match_requested=False
            else:
                opening=False
            self.view_left=False
            if bio:self.bio_signature=bio
            newly_friended=friendship and self.key not in self.friends
            if friendship:self.friends.add(self.key)
            if opening:
                # Reserve the greeting job before incoming messages can schedule replies.
                await self.ingest(self.key,"AnonChat - "+identity,None,False)
                await self.new_chat(self.key,"\n".join(bio)[:800])
            await self.record(root,identity,first=new and not opening)
            if friendship and identity not in {"New partner","Partner"}:
                self.friend_keys[identity]=self.key
            if newly_friended:
                if self.lifecycle:await self.lifecycle(self.key,"friend",identity)
            self.request_pending=self.request_pending or any("sent a friend request" in label.lower() for label in labels)
        if (home or ended) and self.key and self.key not in self.retired:
            self.retired.add(self.key)
            if self.lifecycle:await self.lifecycle(self.key,"ended")
            self.awaiting_match=self.saw_gap=True
        if not allow_actions or not self.auto_enabled() or self.blocked or time.monotonic()-self.last_action<=4:
            return
        accepts=[n for n in root.iter("node") if n.get("package")==self.package
            and n.get("clickable")=="true" and (n.get("content-desc") or n.get("text")) in
            {"Accept friend request","Accept friendship request"}]
        if len(accepts)==1:
            await self.tap(accepts[0]);self.last_action=time.monotonic();return
        if (home or ended or friendship) and self.ready_to_leave(self.key):
            targets=nodes(root,self.settings.selectors.get("search" if home else "next"))
            if len(targets)==1:
                if self.key:self.retired.add(self.key)
                await self.tap(targets[0])
                self.last_action=time.monotonic()
                self.awaiting_match=self.saw_gap=True
            elif friendship:
                # Friend conversations use the search tab instead of a Next button.
                # process() already owns the device transaction; do not acquire it again.
                self.last_action=time.monotonic()
                await self.match_view(root,"search")

    async def poll(self):
        last_error=None
        while True:
            try:
                async with self.polling_session() as allowed:
                    if allowed:
                        root=await self.dump()
                        await self.process(root)
                last_error=None
            except asyncio.CancelledError:
                raise
            except Exception as error:
                message=f"AnonChat: {error}"
                if message!=last_error:
                    self.status(message)
                    last_error=message
                # A read failure does not poison future successful reads.
            await asyncio.sleep(self.settings.adb_poll_seconds)

    async def tap(self,node):
        x,y=center(node)
        await self.shell(f"input tap {x} {y}")

    async def send(self,key,text,reply_to=None):
        try:
            return await self._send(key,text,reply_to)
        except ForegroundDeferred:
            raise
        except Exception as error:
            if not self.blocked:
                raise SendRejected(str(error)) from error
            raise

    def validate_target(self,root,key,baseline=None,bio=None):
        identity,current=snapshot(root,self.settings.selectors)
        if key!=self.key or identity!=self.identity or key in self.retired or self.identity_ambiguous:
            raise ValueError("AnonChat conversation changed; operation cancelled.")
        signature=tuple(n.get("text") or n.get("content-desc","") for n in nodes(root,self.settings.selectors.get("bio")))
        expected=self.bio_signature if bio is None else bio
        if signature and expected and signature!=expected:
            raise ValueError("Partner biography changed; operation cancelled.")
        previous=self.previous if baseline is None else baseline
        if previous:tail_delta(previous,current)
        if key not in self.friends and self.system_labels(root) & {"Chat was ended by your partner","Your partner ended chat","The partner ended chat","You ended chat"}:
            raise ValueError("Chat closed; nothing was submitted.")
        return identity,current

    async def _send(self,key,text,reply_to=None):
        command=input_command(text)
        async with self.session():
            if self.identity_ambiguous:
                raise ValueError("Conversation identity needs verification; no message was submitted.")
            if self.blocked:
                raise ValueError("ADB state needs inspection/reconnection before sending.")
            root=await self.dump()
            identity,before=self.validate_target(root,key)
            if key not in self.friends and self.system_labels(root) & {"Chat was ended by your partner","Your partner ended chat","The partner ended chat","You ended chat"}:
                raise ValueError("Chat closed; no message was submitted.")
            if key!=self.key or identity!=self.identity or key in self.retired:
                raise ValueError("AnonChat conversation changed; sending cancelled.")
            signature=tuple(n.get("text") or n.get("content-desc","") for n in nodes(root,self.settings.selectors.get("bio")))
            if signature and self.bio_signature and signature!=self.bio_signature:
                raise ValueError("Partner biography changed; sending cancelled.")
            if self.previous:
                tail_delta(self.previous,before)
            entry=unique(root,self.settings.selectors.get("input"),"message input")
            if entry.get("text","").strip() not in ("",self.settings.selectors.get("input_placeholder")):
                raise ValueError("Android input is not empty. Clear it manually before sending.")
            self.pending_send={"key":key,"text":text,"before":before}
            try:
                if reply_to:
                    await self.message_menu(root,key,reply_to,"Reply")
                    root=await self.dump()
                    quoted=next(m.text for m in self.visible_messages if m.id==reply_to)
                    if not any((n.get("text") or n.get("content-desc"))==quoted for n in root.iter("node")
                               if n not in nodes(root,self.settings.selectors.get("incoming"))+nodes(root,self.settings.selectors.get("outgoing"))):
                        raise ValueError("Reply preview could not be verified; inspect Android before sending.")
                    entry=unique(root,self.settings.selectors.get("input"),"message input")
                await self.tap(entry)
                await self.shell(command)
                root=await self.dump()
                identity,_=self.validate_target(root,key,baseline=before,bio=signature)
                entry=unique(root,self.settings.selectors.get("input"),"message input")
                if identity!=self.identity or entry.get("text")!=text:
                    raise ValueError("Typed text or conversation did not match; unsent input needs inspection.")
                await self.tap(unique(root,self.settings.selectors.get("send"),"send button"))
                for _ in range(5):
                    await asyncio.sleep(0.3)
                    root=await self.dump()
                    identity,after=snapshot(root,self.settings.selectors)
                    if identity!=self.identity:
                        break
                    delta=tail_delta(before,after)
                    if ("assistant",text) in delta:
                        await self.process(root,allow_actions=False)
                        # process() already inserted the actual outgoing occurrence.
                        self.pending_send=None
                        return None
                raise ValueError("ADB submission is unverified. Inspect the conversation; do not blindly resend.")
            except BaseException:
                self.blocked=True
                raise

    async def match(self,action):
        if action not in {"search","next","end"}:
            raise ValueError("Unsupported matching action.")
        async with self.session():
            root=await self.dump()
            await self.match_view(root,action)

    async def match_view(self,root,action):
        # The caller holds the shared device lock for this complete transition.
        # Continue a temporary partner, but leave a promoted friend for new matching.
        identities=nodes(root,self.settings.selectors.get("identity"))
        same_header=len(identities)==1 and identities[0].get("text","").strip()==self.identity
        friend_view=(same_header and self.key in self.friends) or bool(self.system_labels(root) & {
            "You and your partner became friends","The partner accepted your friend request",
            "The partner has accepted your friend request","You are now friends"})
        if action in {"search","next"} and friend_view:
            from .anon_xml import navigation
            tabs=navigation(root)
            if len(tabs)!=3:raise LayoutError("Open the AnonChat search tab; navigation XML is unavailable.")
            await self.process(root,allow_actions=False)
            await self.tap(tabs[0])
            root=await self.dump()
            action="search"
            if nodes(root,self.settings.selectors.get("identity")) and self.system_labels(root) & {"You and your partner became friends","You are now friends"}:
                raise LayoutError("AnonChat has not opened the search tab yet; waiting.")
        if action=="search" and nodes(root,self.settings.selectors.get("identity")):
            labels=self.system_labels(root)
            closed=bool(labels & {"Chat was ended by your partner","Your partner ended chat","The partner ended chat","You ended chat"})
            if not closed:
                await self.process(root,allow_actions=False)
                return
            action="next"
        if action=="search" and not nodes(root,self.settings.selectors.get("search")):
            # AnonChat's search tab is the left item of its bottom navigation,
            # identified structurally from fresh XML, not stored desktop coordinates.
            from .anon_xml import navigation
            tabs=navigation(root)
            if len(tabs)!=3:raise LayoutError("Open the AnonChat search tab; navigation XML is unavailable.")
            await self.tap(tabs[0])
            root=await self.dump()
            if nodes(root,self.settings.selectors.get("identity")):
                await self.process(root,allow_actions=False)
                return
        if action=="end":
            target=unique(root,{"package":self.package,"content-desc":"End chat","clickable":"true"},"End chat")
        else:
            target=unique(root,self.settings.selectors.get(action),action)
        await self.tap(target)
        if self.key:
            self.retired.add(self.key)
            if self.lifecycle and self.key not in self.friends:await self.lifecycle(self.key,"ended")
        self.awaiting_match=action!="end"
        self.match_requested=action!="end"
        self.saw_gap=False
        self.last_action=time.monotonic()

    async def message_menu(self,root,key,message_id,action):
        self.validate_target(root,key)
        message=next((m for m in self.visible_messages if m.id==message_id),None)
        if message is None:
            raise ValueError("Message is no longer available in this Android view.")
        selector=self.settings.selectors.get("outgoing" if message.role=="assistant" else "incoming")
        candidates=[n for n in nodes(root,selector) if n.get("text")==message.text]
        if len(candidates)!=1:
            raise ValueError("Selected message is absent or duplicated; action cancelled.")
        x,y=center(candidates[0])
        await self.shell(f"input swipe {x} {y} {x} {y} 650")
        menu=await self.dump()
        options=[n for n in menu.iter("node") if (n.get("text") or n.get("content-desc"))==action]
        if len(options)!=1:
            await self.shell("input keyevent 4")
            raise ValueError(f"AnonChat did not expose a unique {action} action in XML.")
        await self.tap(options[0])

    async def reconcile(self,key):
        pending=self.pending_send
        if not pending or pending['key']!=key:
            raise ValueError("No pending submission is available for this conversation.")
        async with self.session():
            root=await self.dump()
            identity,after=self.validate_target(root,key,baseline=pending["before"])
            if key!=self.key or identity!=self.identity:
                raise ValueError("Open the original conversation before checking its submission.")
            delta=tail_delta(pending['before'],after)
            if delta.count(('assistant',pending['text']))!=1:
                raise ValueError("Send remains unverified. Inspect the Android draft/history; nothing was resent.")
            await self.process(root,allow_actions=False)
            self.pending_send=None
            self.blocked=False

    async def delete(self,key,message):
        async with self.session():
            if self.blocked:
                raise ValueError("Inspect the Android state first.")
            root=await self.dump()
            await self.message_menu(root,key,message.id,"Delete")
            # Never guess a destructive confirmation dialog.
            root=await self.dump()
            identity,current=snapshot(root,self.settings.selectors)
            if identity!=self.identity or ("assistant",message.text) in current:
                raise ValueError("Deletion was not verified; inspect the Android confirmation dialog.")
            self.previous=current
            self.visible_messages=[m for m in self.visible_messages if m.id!=message.id]

    @asynccontextmanager
    async def typing(self,key):
        yield

    async def close(self):
        if self.bridge is not None:
            self.bridge.unwatch(self.settings.selectors.get("package"))
        if self.poll_task:
            self.poll_task.cancel()
            await asyncio.gather(self.poll_task,return_exceptions=True)
        self.device=None
