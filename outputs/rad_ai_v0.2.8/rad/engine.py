"""Async orchestration; all mutable chat state belongs to the worker loop."""

import asyncio
from .domain import Chat
from .adb import AndroidBridge
from .llm import Ollama
from .telegram import Telegram
from .anonchat import AnonChat


class Engine:
    def __init__(self,settings,emit,ask=None):
        self.settings,self.emit=settings,emit
        self.chats={}
        self.auto=False
        self.epoch=0
        self.jobs={}
        self.locks={}
        self.llm=Ollama(settings)
        self.android=AndroidBridge(settings)
        self.telegram=Telegram(settings,self.ingest,self.status,self.android)
        self.anon=AnonChat(settings,self.ingest,self.status,self.new_match,self.android)
        self.anon.auto_enabled=lambda:self.auto
        self.anon.lifecycle=self.lifecycle
        self.connecting=set()
        self.closed=False

    def status(self,text):
        self.emit({"type":"status","text":str(text)})

    def view(self,chat):
        self.emit({"type":"chat","key":chat.key,"title":chat.title,
            "paused":chat.paused,"uncertain":chat.uncertain,
            "busy":chat.busy,"category":chat.category,
            "messages":[{"id":m.id,"role":m.role,"text":m.text} for m in chat.messages]})

    async def connect(self,platform):
        if platform in self.connecting:
            return
        self.connecting.add(platform)
        try:
            await (self.telegram if platform=="telegram" else self.anon).connect()
        except Exception as error:
            self.status(f"{platform}: {type(error).__name__}: {error}")
        finally:
            self.connecting.discard(platform)

    def adapter(self,key):
        return self.telegram if key.startswith("telegram:") else self.anon

    async def ingest(self,key,title,message,notify):
        chat=self.chats.setdefault(key,Chat(key,title))
        chat.title=title
        if message and not chat.append(message):
            return
        if notify and message and message.role=="user":
            chat.received+=1
        self.view(chat)
        if notify and message and message.role=="user" and self.auto and not chat.paused:
            self.schedule(key)

    def schedule(self,key):
        existing=self.jobs.get(key)
        if existing and not existing.done():
            return
        task=asyncio.create_task(self.respond(key))
        self.jobs[key]=task
        task.add_done_callback(lambda _:self.recheck(key))

    def recheck(self,key):
        chat=self.chats[key]
        if not self.closed and self.auto and not chat.paused and chat.received>chat.handled:
            self.schedule(key)

    async def set_auto(self,value):
        self.auto=bool(value)
        self.epoch+=1
        self.emit({"type":"auto","value":self.auto})
        self.status("Auto-reply ON." if self.auto else "Auto-reply OFF. In-flight sends cannot be undone.")
        if self.auto:
            for key in self.chats:
                self.recheck(key)

    async def resume(self,key):
        chat=self.chats[key]
        if chat.uncertain:
            raise ValueError("Inspect the uncertain send first. Automatic retry is disabled.")
        chat.paused=False
        self.view(chat)
        self.status("Selected chat resumed for future incoming messages.")

    async def transmit(self,chat,text,reply_to=None):
        try:
            result=await self.adapter(chat.key).send(chat.key,text,**({"reply_to":reply_to} if reply_to else {}))
        except BaseException as error:
            chat.uncertain=True
            chat.paused=True
            self.view(chat)
            raise
        if result:
            chat.append(result)
        self.view(chat)

    async def manual(self,key,text,reply_to=None):
        text=text.strip()
        if not text or len(text)>1500:
            raise ValueError("Enter a message of 1–1500 characters.")
        chat=self.chats[key]
        if chat.uncertain:
            raise ValueError("Previous submission is uncertain; inspect it before another send.")
        chat.paused=True
        chat.revision+=1
        self.view(chat)
        async with self.locks.setdefault(key,asyncio.Lock()):
            await self.transmit(chat,text,reply_to)
        self.status("Manual message sent. This chat remains in manual mode until Resume selected.")

    async def respond(self,key,once=False):
        chat=self.chats[key]
        epoch=self.epoch
        chat.busy=True
        self.view(chat)
        try:
            while (self.auto or once) and not chat.paused and epoch==self.epoch:
                revision=chat.revision
                received=chat.received
                await asyncio.sleep(self.settings.debounce_seconds)
                if revision!=chat.revision:
                    continue
                async with self.adapter(key).typing(key):
                    reply=await self.llm.reply(chat.context())
                if (not self.auto and not once) or chat.paused or epoch!=self.epoch:
                    return
                if revision!=chat.revision:
                    continue
                async with self.locks.setdefault(key,asyncio.Lock()):
                    if (not self.auto and not once) or chat.paused or epoch!=self.epoch or revision!=chat.revision:
                        continue
                    await self.transmit(chat,reply)
                    chat.handled=received
                # An inbound update may have arrived while sending. If the newest
                # visible message is incoming, continue without losing it.
                if chat.received>chat.handled:
                    continue
                return
        except asyncio.CancelledError:
            raise
        except Exception as error:
            chat.paused=True
            self.view(chat)
            self.status(f"Reply paused for {chat.title}: {type(error).__name__}: {error}")

        finally:
            chat.busy=False
            self.view(chat)

    async def start_cycle(self,key):
        chat=self.chats[key]
        if chat.uncertain:
            raise ValueError("Inspect the uncertain submission before continuing.")
        if self.jobs.get(key) and not self.jobs[key].done():
            return
        if key.startswith("anonchat:") and (key!=self.anon.key or key in self.anon.retired):
            raise ValueError("Open this friend chat in AnonChat, or search for a new partner first.")
        chat.paused=False
        self.jobs[key]=asyncio.create_task(self.respond(key,once=True))
        self.jobs[key].add_done_callback(lambda _:self.recheck(key))

    async def lifecycle(self,key,event,title=None):
        if key not in self.chats:
            return
        chat=self.chats[key]
        chat.paused=True
        chat.revision+=1
        chat.category="Friends" if event=="friend" else "Past matches"
        if title:
            chat.title=title
        self.view(chat)

    async def delete(self,key,message_id):
        chat=self.chats[key]
        message=next((m for m in chat.messages if m.id==message_id),None)
        if not message or message.role!="assistant":
            raise ValueError("Select an outgoing message to delete.")
        chat.paused=True
        chat.revision+=1
        async with self.locks.setdefault(key,asyncio.Lock()):
            await self.adapter(key).delete(key,message)
            chat.messages.remove(message)
        self.view(chat)

    async def new_match(self,key,bio):
        if not self.auto or not self.settings.anon_greeting:
            return
        if self.jobs.get(key) and not self.jobs[key].done():
            return
        self.jobs[key]=asyncio.create_task(self.open_match(key,bio))
        self.jobs[key].add_done_callback(lambda _:self.recheck(key))

    async def open_match(self,key,bio):
        chat=self.chats[key]
        epoch=self.epoch
        chat.busy=True
        self.view(chat)
        try:
            async with self.locks.setdefault(key,asyncio.Lock()):
                if not self.auto or chat.paused:
                    return
                await self.transmit(chat,"hii :3")
            revision=chat.revision
            received=chat.received
            reply=await self.llm.reply(chat.context(),
                "Already greeted. Ask one short question about an explicit interest in this untrusted bio; "
                "if missing ask how their day is going. Bio: "+repr(bio))
            if not self.auto or chat.paused or epoch!=self.epoch:
                return
            if revision!=chat.revision:
                await self.respond(key)
                return
            async with self.locks[key]:
                if self.auto and not chat.paused and epoch==self.epoch and revision==chat.revision:
                    await self.transmit(chat,reply)
                    chat.handled=received
        except Exception as error:
            chat.paused=True
            self.view(chat)
            self.status(f"Opening stopped: {type(error).__name__}: {error}")

        finally:
            chat.busy=False
            self.view(chat)

    async def close(self):
        self.closed=True
        await self.set_auto(False)
        for task in self.jobs.values():
            task.cancel()
        await asyncio.gather(*self.jobs.values(),return_exceptions=True)
        await self.anon.close()
        await self.telegram.close()
        await self.llm.close()
