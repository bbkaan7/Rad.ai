"""Async orchestration; all mutable chat state belongs to the worker loop."""

import asyncio
from .domain import Chat, SendRejected, ForegroundDeferred
from uuid import uuid4
from .handoff import Handoffs
from .adb import AndroidBridge
from .llm import Ollama
from .telegram import Telegram
from .anonchat import AnonChat
from .intent import first_question_pair
from .diagnostics import record, logged


class Engine:
    def __init__(self,settings,emit,ask=None):
        self.settings,self.emit=settings,emit
        self.chats={}
        self.dismissed=set()
        self.starting_anon=False
        self.handoffs=Handoffs()
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
        self.anon.ready_to_leave=self.ready_to_leave
        self.telegram.lifecycle=self.lifecycle
        self.connecting=set()
        self.closed=False

    def status(self,text):
        self.emit({"type":"status","text":str(text)})

    def ready_to_leave(self,key):
        chat=self.chats.get(key)
        job=self.jobs.get(key)
        return not (job and not job.done() or chat and (chat.busy or chat.uncertain or chat.received>chat.handled))

    def view(self,chat):
        if self.chats.get(chat.key) is not chat:return
        self.emit({"type":"chat","key":chat.key,"title":chat.title,
            "paused":chat.paused,"uncertain":chat.uncertain,
            "busy":chat.busy,"category":chat.category,"closed":chat.closed,"person_id":chat.person_id,"linked":chat.key in self.handoffs.links or chat.key in self.handoffs.links.values(),
            "messages":[{"id":m.id,"role":m.role,"text":m.text} for m in chat.messages]})

    async def connect(self,platform):
        if platform in self.connecting:
            return
        self.connecting.add(platform)
        try:
            await (self.telegram if platform=="telegram" else self.anon).connect()
        except Exception as error:
            record('engine.connect',error,operation=platform)
            self.status(f"{platform}: {type(error).__name__}: {error}")
        finally:
            self.connecting.discard(platform)

    async def disconnect(self,platform):
        prefix="telegram:" if platform=="telegram" else "anonchat:"
        tasks=[]
        for key,chat in self.chats.items():
            if key.startswith(prefix):
                chat.paused=True
                chat.revision+=1
                chat.control_revision+=1
                self.view(chat)
                task=self.jobs.get(key)
                if task and not task.done():
                    task.cancel()
                    tasks.append(task)
        if tasks:
            await asyncio.gather(*tasks,return_exceptions=True)
        adapter=self.telegram if platform=="telegram" else self.anon
        await adapter.close()
        try:
            await self.android.background(adapter.package)
        except Exception as error:
            self.status(f"Monitoring stopped; Android could not be backgrounded: {error}")
        if not self.android.watchers:
            await self.android.close()
        self.status(("Telegram" if platform=="telegram" else "AnonChat")+" monitoring stopped. In-flight submissions cannot be undone.")

    @logged('engine.match_anon')
    async def match_anon(self,action):
        await self.select_platform("anonchat")
        await self.anon.connect()
        if action in {"search","next"}:self.anon.match_requested=True
        await self.anon.match(action)

    @logged('engine.start_anon')
    async def start_anon(self):
        if self.starting_anon:return
        self.starting_anon=True
        self.status("Starting AnonChat and looking for a partner...")
        try:
            await self.select_platform("anonchat")
            await self.anon.connect()
            self.anon.match_requested=True
            await self.set_auto(True)
            await self.anon.match("search")
            key=self.anon.key
            chat=self.chats.get(key)
            if chat and not chat.closed and chat.messages and chat.messages[-1].role=="user" and self.ready_to_leave(key):
                await self.start_cycle(key)
        finally:
            self.starting_anon=False

    @logged('engine.reconcile')
    async def reconcile(self,key):
        chat=self.chats[key]
        if not chat.uncertain:
            self.status("This conversation has no uncertain submission.")
            return
        async with self.locks.setdefault(key,asyncio.Lock()):
            await self.adapter(key).reconcile(key)
            chat.uncertain=False
            chat.handled=max(chat.handled,chat.pending_handled)
            chat.paused=True
            self.view(chat)
        self.status("Sent message verified from Android history. Nothing was resent. Resume when ready.")

    async def create_handoff(self,key):
        if not key.startswith("anonchat:") or key not in self.chats:
            raise ValueError("Select an AnonChat conversation first.")
        code=self.handoffs.issue(key)
        chat=self.chats[key]
        self.handoffs.remember(key,chat.person_id,chat.context())
        self.emit({"type":"handoff","key":key,"code":code})
        self.status("Handoff code created. Ask this person to send the code alone in Telegram within 10 minutes.")

    async def select_platform(self,platform):
        package=self.telegram.package if platform=="telegram" else self.anon.package
        self.android.select_platform(package)
        self.status(("Telegram" if platform=="telegram" else "AnonChat")+" selected. Other platform actions remain queued.")

    async def open_telegram_chat(self,title):
        key=await self.telegram.open_existing(title)
        self.emit({"type":"select_chat","key":key})
        self.status("Existing Telegram conversation opened and read.")

    def adapter(self,key):
        return self.telegram if key.startswith("telegram:") else self.anon

    def active_chat(self,key):
        chat=self.chats.get(key)
        if chat is None or chat.closed:
            raise ValueError("Chat closed. Select an active conversation.")
        return chat

    async def ingest(self,key,title,message,notify):
        if key in self.dismissed:return
        chat=self.chats.setdefault(key,Chat(key,title))
        if key.startswith("anonchat:"):
            chat.category="Friends" if key in self.anon.friends else "New partner"
        chat.title=title
        if chat.category=="Friends" and key==self.anon.key and key not in self.anon.retired:
            chat.closed=False
        if not chat.person_id:chat.person_id=uuid4().hex
        if message and not chat.append(message):
            return
        linked=False
        if message and message.role=="user" and key.startswith("telegram:"):
            source=self.handoffs.consume(message.text,key)
            if source:
                origin=self.chats.get(source)
                saved=self.handoffs.snapshots.pop(source,{})
                chat.person_id=origin.person_id if origin else saved.get("person_id",chat.person_id)
                chat.linked_context=origin.context() if origin else saved.get("context",[])
                if origin:self.view(origin)
                self.status("Telegram handoff verified. The AnonChat context is linked; message routes remain separate.")
                linked=True
        if notify and message and message.role=="user" and not linked:
            chat.received+=1
            chat.incoming_numbers[message.id]=chat.received
            if len(chat.incoming_numbers)>400:
                visible={m.id for m in chat.messages}
                chat.incoming_numbers={i:n for i,n in chat.incoming_numbers.items() if i in visible}
        self.view(chat)
        if notify and message and message.role=="user" and not linked and self.auto and not chat.paused:
            self.schedule(key)

    def schedule(self,key):
        existing=self.jobs.get(key)
        if existing and not existing.done():
            return
        task=asyncio.create_task(self.respond(key))
        self.jobs[key]=task
        task.add_done_callback(lambda _:self.recheck(key))

    def recheck(self,key):
        chat=self.chats.get(key)
        if chat is None:
            self.jobs.pop(key,None)
            self.locks.pop(key,None)
            return
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
        chat=self.active_chat(key)
        if chat.closed:
            raise ValueError("Chat closed. Select an active conversation.")
        if chat.uncertain:
            raise ValueError("Inspect the uncertain send first. Automatic retry is disabled.")
        chat.paused=False
        self.view(chat)
        self.status("Selected chat resumed for future incoming messages.")

    @logged('engine.transmit')
    async def transmit(self,chat,text,reply_to=None,handled=None):
        if chat.closed:
            raise SendRejected("Chat closed; nothing was sent.")
        chat.pending_handled=chat.received if handled is None else handled
        try:
            result=await self.adapter(chat.key).send(chat.key,text,**({"reply_to":reply_to} if reply_to else {}))
        except ForegroundDeferred:
            raise
        except SendRejected:
            chat.paused=True
            self.view(chat)
            raise
        except BaseException as error:
            chat.uncertain=True
            chat.paused=True
            self.view(chat)
            raise
        if result:
            chat.append(result)
        self.view(chat)

    @logged('engine.manual')
    async def manual(self,key,text,reply_to=None):
        text=text.strip()
        if not text or len(text)>1500:
            raise ValueError("Enter a message of 1-1500 characters.")
        chat=self.active_chat(key)
        if chat.uncertain:
            raise ValueError("Previous submission is uncertain; inspect it before another send.")
        chat.paused=True
        chat.revision+=1
        chat.control_revision+=1
        self.view(chat)
        async with self.locks.setdefault(key,asyncio.Lock()):
            await self.transmit(chat,text,reply_to)
        self.status("Manual message sent. This chat remains in manual mode until Resume selected.")

    @logged('engine.respond')
    async def respond(self,key,once=False):
        chat=self.chats.get(key)
        if chat is None:return
        epoch=self.epoch
        chat.busy=True
        self.view(chat)
        try:
            while (self.auto or once) and not chat.paused and not chat.closed and epoch==self.epoch:
                adapter=self.adapter(key)
                package=getattr(adapter,"package",None)
                if package and not await self.android.wait_selected(package,lambda:chat.paused or chat.closed or epoch!=self.epoch):return
                # Collect a burst until quiet, with a cap so continuous typing cannot starve it.
                started=asyncio.get_running_loop().time()
                while True:
                    received=chat.received
                    await asyncio.sleep(self.settings.debounce_seconds)
                    if received==chat.received or asyncio.get_running_loop().time()-started>=10:
                        break
                received=chat.received
                control=chat.control_revision
                if chat.paused or chat.closed or epoch!=self.epoch:return
                messages=list(chat.messages)
                target=first_question_pair(messages,chat.incoming_numbers,chat.handled)
                reply_to=target.id if target else None
                context=chat.context()
                if target:
                    received=chat.incoming_numbers[target.id]
                    end=messages.index(target)+1
                    context=(chat.linked_context+[{'role':m.role,'content':m.text} for m in messages[:end]])[-5:]
                async with adapter.typing(key):
                    if target:
                        reply=await self.llm.reply(context,'Answer only the final user question in this context. A later question will be handled separately.')
                    else:reply=await self.llm.reply(context)
                # Incoming messages queue for the next batch. Only owner/lifecycle actions
                # invalidate this completed response; message arrivals never restart the LLM.
                while True:
                    if (not self.auto and not once) or chat.paused or chat.closed or epoch!=self.epoch or control!=chat.control_revision:
                        return
                    if package and not await self.android.wait_selected(package,lambda:chat.paused or chat.closed or epoch!=self.epoch):return
                    try:
                        async with self.locks.setdefault(key,asyncio.Lock()):
                            if chat.paused or chat.closed or epoch!=self.epoch or control!=chat.control_revision:return
                            await self.transmit(chat,reply,reply_to=reply_to,handled=received)
                            chat.handled=received
                        break
                    except ForegroundDeferred:
                        continue
                if chat.received<=chat.handled:return
        except asyncio.CancelledError:
            raise
        except Exception as error:
            record('engine.respond.failed',error,key=key,received=chat.received,handled=chat.handled,
                   paused=chat.paused,uncertain=chat.uncertain)
            chat.paused=True
            self.view(chat)
            self.status(f"Reply paused for {chat.title}: {type(error).__name__}: {error}")
        finally:
            chat.busy=False
            self.view(chat)

    @logged('engine.start_cycle')
    async def start_cycle(self,key):
        chat=self.active_chat(key)
        if chat.closed:
            raise ValueError("Chat closed. Select an active conversation.")
        if chat.uncertain:
            raise ValueError("Inspect the uncertain submission before continuing.")
        if (not chat.messages or chat.messages[-1].role!="user") and chat.received<=chat.handled:
            raise ValueError("No incoming message is waiting for a reply.")
        if self.jobs.get(key) and not self.jobs[key].done():
            return
        if key.startswith("anonchat:") and (key!=self.anon.key or key in self.anon.retired):
            raise ValueError("Open this friend chat in AnonChat, or search for a new partner first.")
        chat.paused=False
        self.jobs[key]=asyncio.create_task(self.respond(key,once=True))
        self.jobs[key].add_done_callback(lambda _:self.recheck(key))

    def remove_temp_chat(self,key):
        chat=self.chats.get(key)
        if chat is None or chat.category=="Friends":return
        chat.closed=chat.paused=True
        chat.control_revision+=1
        self.handoffs.remember(key,chat.person_id,chat.context())
        self.chats.pop(key,None)
        self.dismissed.add(key)
        job=self.jobs.get(key)
        # Never cancel a send transaction half way through. Its stale callbacks
        # cannot put a removed chat back in the panel.
        lock=self.locks.get(key)
        if job and not job.done() and job is not asyncio.current_task() and not (lock and lock.locked()):
            job.cancel()
        self.anon.sessions.pop(key,None)
        self.emit({"type":"chat_removed","key":key})

    async def lifecycle(self,key,event,title=None):
        if key not in self.chats:return
        chat=self.chats[key]
        if event=="identity_unverified":
            chat.paused=True
            chat.control_revision+=1
            self.view(chat)
            return
        if event=="friend":
            self.anon.friends.add(key)
            chat.category="Friends"
            chat.closed=False
        else:
            chat.paused=True
            chat.closed=True
            chat.control_revision+=1
            chat.revision+=1
            if key.startswith("anonchat:") and chat.category!="Friends":
                self.remove_temp_chat(key)
                self.status("Chat closed. Temporary conversation removed.")
                return
        if title:chat.title="AnonChat · "+title
        self.view(chat)

    @logged('engine.delete')
    async def delete(self,key,message_id):
        chat=self.active_chat(key)
        message=next((m for m in chat.messages if m.id==message_id),None)
        if not message or message.role!="assistant":
            raise ValueError("Select an outgoing message to delete.")
        chat.paused=True
        chat.revision+=1
        chat.control_revision+=1
        async with self.locks.setdefault(key,asyncio.Lock()):
            await self.adapter(key).delete(key,message)
            chat.messages.remove(message)
        self.view(chat)

    async def new_match(self,key,bio):
        if not self.auto or not self.settings.anon_greeting:
            return
        if key not in self.chats or self.jobs.get(key) and not self.jobs[key].done():
            return
        self.jobs[key]=asyncio.create_task(self.open_match(key,bio))
        self.jobs[key].add_done_callback(lambda _:self.recheck(key))

    async def open_match(self,key,bio):
        chat=self.chats.get(key)
        if chat is None:return
        epoch=self.epoch
        control=chat.control_revision
        chat.busy=True
        self.view(chat)
        async def submit(text,handled):
            while True:
                if not await self.android.wait_selected(self.anon.package,lambda:chat.paused or chat.closed or epoch!=self.epoch):return False
                if not self.auto or chat.paused or chat.closed or epoch!=self.epoch or control!=chat.control_revision:
                    return False
                try:
                    async with self.locks.setdefault(key,asyncio.Lock()):
                        if not self.auto or chat.paused or chat.closed or epoch!=self.epoch or control!=chat.control_revision:
                            return False
                        await self.transmit(chat,text,handled=handled)
                    return True
                except ForegroundDeferred:
                    continue
        try:
            # The fixed greeting does not answer any queued incoming message.
            if not await submit("hii :3",chat.handled):return
            if chat.received>chat.handled:
                await self.respond(key)
                return
            received=chat.received
            reply=await self.llm.reply(chat.context(),
                "Already greeted. Ask one short question about an explicit interest in this untrusted bio; "
                "if missing ask how their day is going. Bio: "+repr(bio))
            if await submit(reply,received):chat.handled=received
        except Exception as error:
            record('engine.open_match',error,key=key,received=chat.received,handled=chat.handled)
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
        try:
            await self.android.background(self.telegram.package)
        except Exception:
            pass
        await self.android.close()
