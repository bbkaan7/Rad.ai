"""ADB-only Android XML adapter. Windows cursor and desktop pixels are unused."""

import asyncio
import time
from contextlib import asynccontextmanager
from uuid import uuid4
from .adb import AndroidBridge
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
        self.saw_gap=False
        self.auto_enabled=lambda:False
        self.lifecycle=None
        self.last_action=0
        self.visible_messages=[]
        self.retired=set()
        self.friend_keys={}
        self.bio_signature=None

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
        self.blocked=False
        self.identity,self.key,self.previous=None,None,[]
        self.bridge.watch(s.selectors["package"])
        self.poll_task=asyncio.create_task(self.poll())
        self.status("ADB connected. Waiting for readable AnonChat XML.")

    async def process(self,root):
        # Conversation text must never masquerade as a lifecycle control.
        parents={child:parent for parent in root.iter() for child in parent}
        message_nodes=nodes(root,self.settings.selectors.get("incoming"))+nodes(root,self.settings.selectors.get("outgoing"))
        excluded=set(message_nodes)
        excluded.update(parents[n] for n in message_nodes if n in parents)
        labels={n.get("text") or n.get("content-desc","") for n in root.iter("node") if n not in excluded}
        has_identity=bool(nodes(root,self.settings.selectors.get("identity")))
        home=not has_identity and bool(nodes(root,self.settings.selectors.get("search")))
        ended=bool(labels & {"Your partner ended chat", "The partner ended chat", "You ended chat"})
        friend=bool(labels & {"You and your partner became friends", "The partner accepted your friend request"})
        friend=friend and self.key not in self.retired
        if (home or ended or friend) and self.key and self.key not in self.retired:
            self.retired.add(self.key)
            if self.lifecycle:
                title=None
                identities=nodes(root,self.settings.selectors.get("identity"))
                if friend and identities:
                    title=identities[0].get("text")
                    if title and title not in {"New partner", "Partner"}:
                        self.friend_keys[title]=self.key
                await self.lifecycle(self.key,"friend" if friend else "ended",title)
        if self.auto_enabled() and not self.blocked and time.monotonic()-self.last_action>4:
            accepts=[n for n in root.iter("node") if n not in excluded and n.get("package")==self.settings.selectors.get("package")
                and n.get("clickable")=="true" and (n.get("content-desc") or n.get("text")) in
                {"Accept friend request", "Accept friendship request"}]
            if len(accepts)==1:
                await self.tap(accepts[0])
                self.last_action=time.monotonic()
                return
            targets=nodes(root,self.settings.selectors.get("search" if home else "next")) if home or ended or friend else []
            if len(targets)==1:
                await self.tap(targets[0])
                self.last_action=time.monotonic()
                self.awaiting_match=True
                self.saw_gap=home or ended or friend
                return
        if home or ended or friend or not has_identity:
            if home or ended or friend:
                self.saw_gap=True
                self.awaiting_match=True
            return
        identity,current=snapshot(root,self.settings.selectors)
        bio_signature=tuple(n.get("text") or n.get("content-desc","") for n in nodes(root,self.settings.selectors.get("bio")))
        changed_bio=self.bio_signature is not None and bio_signature!=self.bio_signature
        if self.awaiting_match and identity==self.identity and not self.saw_gap and not changed_bio:
            return
        is_new=identity!=self.identity or self.awaiting_match or changed_bio
        if is_new:
            opening=self.awaiting_match or (self.identity is None and not current)
            self.identity=identity
            self.key=self.friend_keys.get(identity) or "anonchat:"+uuid4().hex
            if identity in self.friend_keys:
                self.retired.discard(self.key)
            self.previous=[]
            self.visible_messages=[]
            self.awaiting_match=False
            self.saw_gap=False
            delta=current
        else:
            opening=False
            try:
                delta=tail_delta(self.previous,current)
            except LayoutError:
                self.previous=current
                self.status("AnonChat history changed or scrolled. Resynchronized without replying to old messages.")
                return
        self.bio_signature=bio_signature
        self.previous=current
        for role,text in delta:
            self.sequence+=1
            message=Message(str(self.sequence),role,text)
            self.visible_messages.append(message)
            await self.ingest(self.key,"AnonChat · "+identity,message,not is_new and role=="user")
        # Empty chats still appear in the control panel.
        await self.ingest(self.key,"AnonChat · "+identity,None,False)
        if opening:
            bio="\n".join(n.get("text") or n.get("content-desc","") for n in nodes(root,self.settings.selectors.get("bio")))[:800]
            await self.new_chat(self.key,bio)

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
        command=input_command(text)
        async with self.session():
            if self.blocked:
                raise ValueError("ADB state needs inspection/reconnection before sending.")
            root=await self.dump()
            identity,before=snapshot(root,self.settings.selectors)
            if key!=self.key or identity!=self.identity or key in self.retired:
                raise ValueError("AnonChat conversation changed; sending cancelled.")
            signature=tuple(n.get("text") or n.get("content-desc","") for n in nodes(root,self.settings.selectors.get("bio")))
            if self.bio_signature is not None and signature!=self.bio_signature:
                raise ValueError("Partner biography changed; sending cancelled.")
            entry=unique(root,self.settings.selectors.get("input"),"message input")
            if entry.get("text","").strip() not in ("",self.settings.selectors.get("input_placeholder")):
                raise ValueError("Android input is not empty. Clear it manually before sending.")
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
                identity,_=snapshot(root,self.settings.selectors)
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
                        await self.process(root)
                        # process() already inserted the actual outgoing occurrence.
                        return None
                raise ValueError("ADB submission is unverified. Inspect the conversation; do not blindly resend.")
            except BaseException:
                self.blocked=True
                raise

    async def match(self,action):
        if action not in {"search","next"}:
            raise ValueError("Unsupported matching action.")
        async with self.session():
            root=await self.dump()
            if action=="search" and nodes(root,self.settings.selectors.get("identity")):
                raise ValueError("A conversation is already open; use Next partner.")
            await self.tap(unique(root,self.settings.selectors.get(action),action))
            if self.key:
                self.retired.add(self.key)
                if self.lifecycle:
                    await self.lifecycle(self.key,"ended")
            self.awaiting_match=True
            self.saw_gap=False
            self.last_action=time.monotonic()

    async def message_menu(self,root,key,message_id,action):
        if key!=self.key or snapshot(root,self.settings.selectors)[0]!=self.identity:
            raise ValueError("Open the original AnonChat conversation first.")
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
