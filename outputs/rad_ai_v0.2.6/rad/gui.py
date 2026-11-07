"""Tk stays on the main thread; async networking runs on a dedicated loop."""

import asyncio
import queue
import threading
import uuid
from concurrent.futures import CancelledError
import customtkinter as ctk
import qrcode
from ayarlar import load, VERSION
from .engine import Engine


class Worker:
    def __init__(self,settings,events):
        self.settings,self.events=settings,events
        self.loop=asyncio.new_event_loop()
        self.ready=threading.Event()
        self.auth={}
        self.thread=threading.Thread(target=self.run,daemon=True)
        self.thread.start()
        self.ready.wait(5)

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.engine=Engine(self.settings,self.events.put,self.ask)
        self.ready.set()
        try:
            self.loop.run_forever()
        finally:
            pending=asyncio.all_tasks(self.loop)
            for task in pending:
                task.cancel()
            self.loop.run_until_complete(asyncio.gather(*pending,return_exceptions=True))
            self.loop.run_until_complete(self.loop.shutdown_asyncgens())
            self.loop.close()

    async def ask(self,label,secret):
        token=uuid.uuid4().hex
        future=self.loop.create_future()
        self.auth[token]=future
        self.events.put({"type":"auth","token":token,"label":label,"secret":secret})
        try:
            value=await asyncio.wait_for(future,180)
            if not value:
                raise ValueError("Login cancelled.")
            return value
        finally:
            self.auth.pop(token,None)

    def answer(self,token,value):
        def finish():
            future=self.auth.get(token)
            if future and not future.done():
                future.set_result(value)
        self.loop.call_soon_threadsafe(finish)

    def submit(self,coroutine):
        future=asyncio.run_coroutine_threadsafe(coroutine,self.loop)
        def done(result):
            try:
                result.result()
            except (CancelledError,asyncio.CancelledError):
                pass
            except Exception as error:
                self.events.put({"type":"status","text":f"{type(error).__name__}: {error}"})
        future.add_done_callback(done)
        return future


class Panel(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"Rad.ai v{VERSION}")
        self.geometry("1040x740")
        self.events=queue.Queue()
        self.chats={}
        self.buttons={}
        self.selected=None
        self.closing=False
        self.qr_dialog=None
        self.worker=Worker(load(),self.events)
        self.grid_columnconfigure(1,weight=1)
        self.grid_rowconfigure(1,weight=1)
        top=ctk.CTkFrame(self)
        top.grid(row=0,column=0,columnspan=2,sticky="ew",padx=12,pady=12)
        ctk.CTkLabel(top,text=f"🐾 Rad.ai  {VERSION}",font=("Arial",22,"bold")).pack(side="left",padx=12)
        self.auto=ctk.CTkSwitch(top,text="Auto-reply: OFF",command=self.toggle)
        self.auto.pack(side="right",padx=12)
        ctk.CTkButton(top,text="Connect Telegram (QR)",command=lambda:self.connect("telegram")).pack(side="left",padx=4)
        ctk.CTkButton(top,text="Connect AnonChat",command=lambda:self.connect("anonchat")).pack(side="left",padx=4)
        self.sidebar=ctk.CTkScrollableFrame(self,width=230,label_text="Active chats")
        self.sidebar.grid(row=1,column=0,sticky="nsew",padx=(12,6))
        right=ctk.CTkFrame(self)
        right.grid(row=1,column=1,sticky="nsew",padx=(6,12))
        right.grid_columnconfigure(0,weight=1)
        right.grid_rowconfigure(1,weight=1)
        self.heading=ctk.CTkLabel(right,text="Select a conversation")
        self.heading.grid(row=0,column=0,sticky="w",padx=12,pady=8)
        self.feed=ctk.CTkTextbox(right,state="disabled",wrap="word")
        self.feed.grid(row=1,column=0,sticky="nsew",padx=12,pady=4)
        controls=ctk.CTkFrame(right)
        controls.grid(row=2,column=0,sticky="ew",padx=12,pady=4)
        ctk.CTkButton(controls,text="Resume selected",command=self.resume).pack(side="left",padx=3)
        for label,action in (("Search partner","search"),("Next partner","next")):
            ctk.CTkButton(controls,text=label,command=lambda a=action:self.worker.submit(self.worker.engine.anon.match(a))).pack(side="left",padx=3)
        self.entry=ctk.CTkTextbox(right,height=85,wrap="word")
        self.entry.grid(row=3,column=0,sticky="ew",padx=12,pady=5)
        ctk.CTkButton(right,text="Send manually (pauses this chat)",command=self.send).grid(row=4,column=0,sticky="e",padx=12,pady=8)
        self.status=ctk.CTkLabel(self,text="Connect a platform. Auto-reply is OFF.",anchor="w",wraplength=980)
        self.status.grid(row=2,column=0,columnspan=2,sticky="ew",padx=12,pady=12)
        self.protocol("WM_DELETE_WINDOW",self.close)
        self.after(60,self.poll)

    def connect(self,platform):
        self.worker.submit(self.worker.engine.connect(platform))

    def toggle(self):
        self.worker.submit(self.worker.engine.set_auto(bool(self.auto.get())))

    def select(self,key):
        self.selected=key
        self.render()

    def render(self):
        if not self.selected:
            return
        chat=self.chats[self.selected]
        state=" — uncertain send" if chat["uncertain"] else " — manual/paused" if chat["paused"] else ""
        self.heading.configure(text=chat["title"]+state)
        self.feed.configure(state="normal")
        self.feed.delete("1.0","end")
        for message in chat["messages"]:
            name="You" if message["role"]=="assistant" else "Contact"
            self.feed.insert("end",f"{name}: {message['text']}\n\n")
        self.feed.configure(state="disabled")
        self.feed.see("end")

    def send(self):
        if not self.selected:
            self.status.configure(text="Select a conversation first.")
            return
        text=self.entry.get("1.0","end").strip()
        if text:
            future=self.worker.submit(self.worker.engine.manual(self.selected,text))
            # Keep the user's draft if submission fails or is uncertain.
            future.add_done_callback(lambda f:self.events.put({"type":"manual_done","text":text}) if not f.cancelled() and f.exception() is None else None)

    def resume(self):
        if self.selected:
            self.worker.submit(self.worker.engine.resume(self.selected))

    def poll(self):
        for _ in range(100):
            try:
                event=self.events.get_nowait()
            except queue.Empty:
                break
            kind=event["type"]
            if kind=="status":
                self.status.configure(text=event["text"])
            elif kind=="auto":
                self.auto.configure(text="Auto-reply: ON" if event["value"] else "Auto-reply: OFF")
            elif kind=="chat":
                key=event["key"]
                self.chats[key]=event
                if key not in self.buttons:
                    button=ctk.CTkButton(self.sidebar,text=event["title"],command=lambda k=key:self.select(k))
                    button.pack(fill="x",pady=4)
                    self.buttons[key]=button
                if self.selected is None:
                    self.selected=key
                if self.selected==key:
                    self.render()
            elif kind=="auth" and not self.closing:
                self.auth_dialog(event)
            elif kind=="qr" and not self.closing:
                self.show_qr(event["url"])
            elif kind=="qr_closed":
                if self.qr_dialog and self.qr_dialog.winfo_exists():
                    self.qr_dialog.destroy()
                self.qr_dialog=None
            elif kind=="manual_done":
                if self.entry.get("1.0","end").strip()==event["text"]:
                    self.entry.delete("1.0","end")
        if not self.closing:
            self.after(60,self.poll)

    def show_qr(self,url):
        if self.qr_dialog and self.qr_dialog.winfo_exists():
            self.qr_dialog.destroy()
        dialog=ctk.CTkToplevel(self)
        self.qr_dialog=dialog
        dialog.title("Telegram QR sign-in")
        dialog.geometry("480x490")
        ctk.CTkLabel(dialog,text="On your signed-in phone: Telegram > Settings > Devices\nLink Desktop Device, then scan this code.",wraplength=440).pack(pady=15)
        image=qrcode.make(url).get_image().convert("RGB")
        dialog.qr_image=ctk.CTkImage(light_image=image,dark_image=image,size=(320,320))
        ctk.CTkLabel(dialog,text="",image=dialog.qr_image).pack(pady=8)
        ctk.CTkLabel(dialog,text="Codes refresh automatically. No SMS is required.\nKeep this login QR private.").pack(pady=8)
        def cancel():
            self.worker.submit(self.worker.engine.telegram.cancel_qr())
            dialog.destroy()
        dialog.protocol("WM_DELETE_WINDOW",cancel)

    def auth_dialog(self,event):
        dialog=ctk.CTkToplevel(self)
        dialog.title("Telegram sign-in")
        dialog.geometry("440x160")
        ctk.CTkLabel(dialog,text=event["label"]).pack(pady=12)
        entry=ctk.CTkEntry(dialog,width=390,show="*" if event["secret"] else "")
        entry.pack(padx=12)
        def finish(value):
            self.worker.answer(event["token"],value)
            dialog.destroy()
        ctk.CTkButton(dialog,text="Continue",command=lambda:finish(entry.get())).pack(pady=12)
        dialog.protocol("WM_DELETE_WINDOW",lambda:finish(None))

    def close(self):
        if self.closing:
            return
        self.closing=True
        self.status.configure(text="Closing connections…")
        future=self.worker.submit(self.worker.engine.close())
        def finish():
            if future.done():
                self.worker.loop.call_soon_threadsafe(self.worker.loop.stop)
                self.destroy()
            else:
                self.after(100,finish)
        finish()


def run():
    ctk.set_appearance_mode("dark")
    ctk.set_default_color_theme("dark-blue")
    Panel().mainloop()
