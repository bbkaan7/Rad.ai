"""ADB-only Android XML adapter. Windows cursor and desktop pixels are unused."""

import asyncio
from contextlib import asynccontextmanager
from uuid import uuid4
from ppadb.client import Client
from .domain import Message, LayoutError, xml_root, snapshot, unique, center, input_command, tail_delta, nodes


class TimedClient(Client):
    def create_connection(self,timeout=None):
        return super().create_connection(timeout=10 if timeout is None else timeout)


class AnonChat:
    def __init__(self, settings, ingest, status, new_chat):
        self.settings,self.ingest,self.status,self.new_chat=settings,ingest,status,new_chat
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

    async def shell(self,command):
        if self.device is None:
            raise ValueError("ADB is not connected.")
        return await asyncio.to_thread(self.device.shell,command,timeout=10)

    async def dump(self):
        # The command is fixed. Chat text can never become shell command syntax.
        result=await self.shell("uiautomator dump /sdcard/rad-ui.xml && cat /sdcard/rad-ui.xml")
        return xml_root(result)

    async def connect(self):
        if self.poll_task and not self.poll_task.done():
            return
        s=self.settings
        if not all(s.selectors.get(key) for key in ("package","identity","incoming","outgoing")):
            raise ValueError("Configure AnonChat package, identity, incoming and outgoing XML selectors in settings.json.")
        client=TimedClient(host=s.adb_host,port=s.adb_port)
        # ppadb uses a separately running Android platform-tools ADB server.
        await asyncio.to_thread(client.remote_connect,s.adb_device_host,s.adb_device_port)
        devices=await asyncio.to_thread(client.devices)
        found=[d for d in devices if not s.adb_serial or d.serial==s.adb_serial]
        if len(found)!=1:
            raise ValueError("Set adb_serial to exactly one connected BlueStacks device.")
        self.device=found[0]
        self.blocked=False
        self.identity,self.key,self.previous=None,None,[]
        self.poll_task=asyncio.create_task(self.poll())
        self.status("ADB connected. Waiting for readable AnonChat XML.")

    async def process(self,root):
        # A supported waiting screen is a lifecycle transition, not a send fault.
        if not nodes(root,self.settings.selectors.get("identity")) and (
                nodes(root,self.settings.selectors.get("search")) or nodes(root,self.settings.selectors.get("next"))):
            self.saw_gap=True
            self.awaiting_match=True
            return
        identity,current=snapshot(root,self.settings.selectors)
        if self.awaiting_match and identity==self.identity and not self.saw_gap:
            return
        is_new=identity!=self.identity or self.awaiting_match
        if is_new:
            opening=self.awaiting_match
            self.identity=identity
            self.key="anonchat:"+uuid4().hex
            self.previous=[]
            self.awaiting_match=False
            self.saw_gap=False
            delta=current
        else:
            opening=False
            delta=tail_delta(self.previous,current)
        self.previous=current
        for role,text in delta:
            self.sequence+=1
            await self.ingest(self.key,"AnonChat · "+identity,
                Message(str(self.sequence),role,text),not is_new and role=="user")
        # Empty chats still appear in the control panel.
        await self.ingest(self.key,"AnonChat · "+identity,None,False)
        if opening:
            bio="\n".join(n.get("text") or n.get("content-desc","") for n in nodes(root,self.settings.selectors.get("bio")))[:800]
            await self.new_chat(self.key,bio)

    async def poll(self):
        last_error=None
        while True:
            try:
                async with self.lock:
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
                self.blocked=True
            await asyncio.sleep(self.settings.adb_poll_seconds)

    async def tap(self,node):
        x,y=center(node)
        await self.shell(f"input tap {x} {y}")

    async def send(self,key,text):
        command=input_command(text)
        async with self.lock:
            if self.blocked:
                raise ValueError("ADB state needs inspection/reconnection before sending.")
            root=await self.dump()
            identity,before=snapshot(root,self.settings.selectors)
            if key!=self.key or identity!=self.identity:
                raise ValueError("AnonChat conversation changed; sending cancelled.")
            entry=unique(root,self.settings.selectors.get("input"),"message input")
            if entry.get("text","").strip() not in ("",self.settings.selectors.get("input_placeholder")):
                raise ValueError("Android input is not empty. Clear it manually before sending.")
            try:
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
        async with self.lock:
            root=await self.dump()
            await self.tap(unique(root,self.settings.selectors.get(action),action))
            self.awaiting_match=True
            self.saw_gap=False
            self.blocked=False

    @asynccontextmanager
    async def typing(self,key):
        yield

    async def close(self):
        if self.poll_task:
            self.poll_task.cancel()
            await asyncio.gather(self.poll_task,return_exceptions=True)
        self.device=None
