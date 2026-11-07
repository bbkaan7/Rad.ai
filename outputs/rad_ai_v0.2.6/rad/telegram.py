"""Normal Telegram account over MTProto; no bot token or Bot API."""

import asyncio
from telethon import TelegramClient, events, functions, errors
from .domain import Message


class Telegram:
    def __init__(self, settings, ingest, status, ask, emit=None):
        self.settings,self.ingest,self.status,self.ask=settings,ingest,status,ask
        self.client=None
        self.presence=None
        self.ready=False
        self.buffer=[]
        self.emit=emit
        self.login_cancel=asyncio.Event()

    async def cancel_qr(self):
        self.login_cancel.set()

    async def qr_auth(self):
        if self.emit is None:
            raise ValueError("QR login needs the control panel. Sign in there first.")
        self.login_cancel.clear()
        try:
            for _ in range(5):
                qr=await self.client.qr_login()
                waiter=asyncio.create_task(qr.wait())
                cancelled=asyncio.create_task(self.login_cancel.wait())
                try:
                    await asyncio.sleep(0)  # Register the update handler before showing the code.
                    self.emit({"type":"qr","url":qr.url})
                    done,_=await asyncio.wait((waiter,cancelled),return_when=asyncio.FIRST_COMPLETED)
                    if cancelled in done:
                        raise ValueError("QR login cancelled.")
                    try:
                        await waiter
                        return
                    except asyncio.TimeoutError:
                        continue
                    except errors.SessionPasswordNeededError:
                        password=await self.ask("Telegram two-step verification password",True)
                        await self.client.sign_in(password=password)
                        return
                finally:
                    waiter.cancel()
                    cancelled.cancel()
                    await asyncio.gather(waiter,cancelled,return_exceptions=True)
            raise ValueError("QR login expired. Connect again to request a fresh code.")
        finally:
            self.emit({"type":"qr_closed"})

    async def connect(self):
        if self.client and self.client.is_connected():
            return
        s=self.settings
        if not s.api_id or not s.api_hash:
            raise ValueError("Configure local Telegram API credentials, then restart Rad.ai.")
        s.session.parent.mkdir(parents=True,exist_ok=True)
        self.client=TelegramClient(str(s.session),s.api_id,s.api_hash,
            flood_sleep_threshold=0,request_retries=1,connection_retries=3)
        async def phone():
            return s.phone or await self.ask("Phone number including country code",False)
        async def code():
            return await self.ask("Telegram login code",True)
        async def password():
            return await self.ask("Telegram two-step verification password",True)
        try:
            if s.telegram_login_method=="qr":
                await self.client.connect()
                if not await self.client.is_user_authorized():
                    await self.qr_auth()
                await self.client.get_me()
            else:
                await self.client.start(phone=phone,code_callback=code,password=password)
            self.client.add_event_handler(self.on_message,events.NewMessage())
            async for dialog in self.client.iter_dialogs(limit=100):
                if not dialog.is_user or getattr(dialog.entity,"bot",False) or dialog.entity.is_self:
                    continue
                messages=await self.client.get_messages(dialog.entity,limit=5)
                for message in reversed(messages):
                    if message.message:
                        await self.ingest(f"telegram:{dialog.id}",dialog.name,
                            Message(str(message.id),"assistant" if message.out else "user",message.message),False)
            self.ready=True
            for event in self.buffer:
                await self.on_message(event)
            self.buffer.clear()
            self.presence=asyncio.create_task(self.keep_online())
            self.status("Telegram connected (normal user account).")
        except BaseException:
            await self.close()
            raise

    async def on_message(self,event):
        if not self.ready:
            self.buffer.append(event)
            return
        if not event.is_private or not event.raw_text:
            return
        entity=await event.get_chat()
        if getattr(entity,"bot",False) or getattr(entity,"is_self",False):
            return
        title=" ".join(filter(None,(getattr(entity,"first_name",""),getattr(entity,"last_name","")))) or str(event.chat_id)
        await self.ingest(f"telegram:{event.chat_id}",title,
            Message(str(event.id),"assistant" if event.out else "user",event.raw_text),not event.out)

    async def keep_online(self):
        while True:
            try:
                await self.client(functions.account.UpdateStatusRequest(offline=False))
                await asyncio.sleep(50)
            except errors.FloodWaitError as error:
                self.status(f"Telegram presence rate-limited for {error.seconds} seconds.")
                await asyncio.sleep(error.seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.status("Telegram presence update failed; retrying after 60 seconds.")
                await asyncio.sleep(60)

    def typing(self,key):
        if not self.ready:
            raise ValueError("Telegram is not connected.")
        return self.client.action(int(key.split(":",1)[1]),"typing")

    async def send(self,key,text):
        if not self.ready:
            raise ValueError("Telegram is not connected.")
        # No automatic application-level retries: a timeout may follow acceptance.
        message=await self.client.send_message(int(key.split(":",1)[1]),text,parse_mode=None)
        return Message(str(message.id),"assistant",text)

    async def close(self):
        self.ready=False
        if self.presence:
            self.presence.cancel()
            await asyncio.gather(self.presence,return_exceptions=True)
            self.presence=None
        if self.client:
            await self.client.disconnect()
