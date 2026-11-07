"""Tk stays on the main thread; async networking runs on a dedicated loop."""

import asyncio
import queue
import threading
from tkinter import messagebox
from concurrent.futures import CancelledError
import customtkinter as ctk
from ayarlar import load, VERSION
from .engine import Engine


class Worker:
    def __init__(self,settings,events):
        self.settings,self.events=settings,events
        self.loop=asyncio.new_event_loop()
        self.ready=threading.Event()
        self.thread=threading.Thread(target=self.run,daemon=True)
        self.thread.start()
        self.ready.wait(5)

    def run(self):
        asyncio.set_event_loop(self.loop)
        self.engine=Engine(self.settings,self.events.put)
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
        self.geometry("1200x820")
        self.events=queue.Queue()
        self.chats={}
        self.buttons={}
        self.selected=None
        self.reply_to=None
        self.message_options={}
        self.closing=False
        self.worker=Worker(load(),self.events)
        self.grid_columnconfigure(1,weight=1)
        self.grid_rowconfigure(1,weight=1)
        top=ctk.CTkFrame(self)
        top.grid(row=0,column=0,columnspan=2,sticky="ew",padx=12,pady=12)
        ctk.CTkLabel(top,text=f"🐾 Rad.ai  {VERSION}",font=("Arial",22,"bold")).pack(side="left",padx=12)
        self.auto=ctk.CTkSwitch(top,text="Auto-reply: OFF",command=self.toggle)
        self.auto.pack(side="right",padx=12)
        ctk.CTkButton(top,text="Connect Telegram (ADB)",command=lambda:self.connect("telegram")).pack(side="left",padx=4)
        ctk.CTkButton(top,text="Connect AnonChat",command=lambda:self.connect("anonchat")).pack(side="left",padx=4)
        ctk.CTkOptionMenu(top,values=["Dark","Light"],width=85,command=self.set_theme).pack(side="left",padx=5)
        self.tabs=ctk.CTkTabview(self,width=260)
        self.tabs.grid(row=1,column=0,sticky="nsew",padx=(12,6))
        self.sections={}
        for platform in ("AnonChat","Telegram"):
            tab=self.tabs.add(platform)
            sidebar=ctk.CTkScrollableFrame(tab)
            sidebar.pack(fill="both",expand=True)
            for category in (("Chats","Friends","Past matches") if platform=="AnonChat" else ("Chats",)):
                section=ctk.CTkFrame(sidebar)
                section.pack(fill="x",pady=5)
                ctk.CTkLabel(section,text=category).pack(anchor="w",padx=8)
                self.sections[(platform,category)]=section
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
        ctk.CTkButton(controls,text="Start cycle",width=100,command=self.start_cycle).pack(side="left",padx=3)
        ctk.CTkButton(controls,text="Resume selected",width=110,command=self.resume).pack(side="left",padx=3)
        for label,action in (("Search partner","search"),("Next partner","next")):
            ctk.CTkButton(controls,text=label,width=110,command=lambda a=action:self.worker.submit(self.worker.engine.anon.match(a))).pack(side="left",padx=3)
        actions=ctk.CTkFrame(right)
        actions.grid(row=3,column=0,sticky="ew",padx=12,pady=4)
        self.message_picker=ctk.CTkOptionMenu(actions,values=["Select a message"],width=260)
        self.message_picker.pack(side="left",padx=3)
        ctk.CTkButton(actions,text="Reply to",width=75,command=self.choose_reply).pack(side="left",padx=3)
        ctk.CTkButton(actions,text="Delete sent",width=90,command=self.delete_message).pack(side="left",padx=3)
        ctk.CTkButton(actions,text="Clear reply",width=85,command=self.clear_reply).pack(side="left",padx=3)
        self.entry=ctk.CTkTextbox(right,height=85,wrap="word")
        self.entry.grid(row=4,column=0,sticky="ew",padx=12,pady=5)
        ctk.CTkButton(right,text="Send manually (pauses this chat)",command=self.send).grid(row=5,column=0,sticky="e",padx=12,pady=8)
        self.status=ctk.CTkLabel(self,text="Connect a platform. Auto-reply is OFF.",anchor="w",wraplength=980)
        self.status.grid(row=2,column=0,columnspan=2,sticky="ew",padx=12,pady=12)
        self.protocol("WM_DELETE_WINDOW",self.close)
        self.set_theme("Dark")
        self.after(60,self.poll)

    def connect(self,platform):
        self.worker.submit(self.worker.engine.connect(platform))

    def toggle(self):
        self.worker.submit(self.worker.engine.set_auto(bool(self.auto.get())))

    def select(self,key):
        self.selected=key
        self.reply_to=None
        self.render()

    def render(self):
        if not self.selected:
            return
        chat=self.chats[self.selected]
        state=" — uncertain send" if chat["uncertain"] else " — manual/paused" if chat["paused"] else ""
        if chat.get("busy"):
            state=" - Typing..."
        if self.reply_to:
            state+=f" - Reply to #{self.reply_to}"
        self.heading.configure(text=chat["title"]+state)
        previous=self.message_picker.get()
        self.message_options={f"#{m['id']} {m['role']}: {m['text'][:35]}":m for m in chat["messages"]}
        options=list(self.message_options) or ["Select a message"]
        self.message_picker.configure(values=options)
        self.message_picker.set(previous if previous in options else options[-1])
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
            key=self.selected
            future=self.worker.submit(self.worker.engine.manual(key,text,self.reply_to))
            # Keep the user's draft if submission fails or is uncertain.
            future.add_done_callback(lambda f:self.events.put({"type":"manual_done","text":text,"key":key}) if not f.cancelled() and f.exception() is None else None)

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
                platform="Telegram" if key.startswith("telegram:") else "AnonChat"
                section=self.sections[(platform,event.get("category","Chats") if platform=="AnonChat" else "Chats")]
                old=self.buttons.get(key)
                if old and old.master!=section:
                    old.destroy()
                    self.buttons.pop(key)
                if key not in self.buttons:
                    button=ctk.CTkButton(section,text=event["title"],command=lambda k=key:self.select(k),
                        fg_color=("#f2b8b1","#705080"),hover_color=("#eaa394","#906499"),text_color=("#35232f","#fff5fa"))
                    button.pack(fill="x",pady=4,padx=4)
                    self.buttons[key]=button
                self.buttons[key].configure(text=event["title"]+(" - Typing..." if event.get("busy") else ""))
                if self.selected is None:
                    self.selected=key
                if self.selected==key:
                    self.render()
            elif kind=="manual_done":
                if self.selected==event["key"] and self.entry.get("1.0","end").strip()==event["text"]:
                    self.entry.delete("1.0","end")
                    self.reply_to=None
                    self.render()
        if not self.closing:
            self.after(60,self.poll)

    def start_cycle(self):
        if self.selected:
            self.worker.submit(self.worker.engine.start_cycle(self.selected))
        elif self.tabs.get()=="AnonChat":
            self.worker.submit(self.worker.engine.anon.match("search"))

    def choose_reply(self):
        message=self.message_options.get(self.message_picker.get())
        if message:
            self.reply_to=message["id"]
            self.render()

    def clear_reply(self):
        self.reply_to=None
        self.render()

    def delete_message(self):
        message=self.message_options.get(self.message_picker.get())
        if not self.selected or not message or message["role"]!="assistant":
            self.status.configure(text="Select one of your outgoing messages first.")
            return
        if messagebox.askyesno("Delete message", "Delete this sent message for both sides where supported?\n\n"+message["text"],parent=self):
            self.worker.submit(self.worker.engine.delete(self.selected,message["id"]))

    def set_theme(self,value):
        ctk.set_appearance_mode(value.lower())
        self.configure(fg_color=("#fff7f5","#17151c"))
        def style(widget):
            for child in widget.winfo_children():
                if isinstance(child,ctk.CTkButton):
                    child.configure(fg_color=("#f2b8b1","#705080"),hover_color=("#eaa394","#906499"),text_color=("#35232f","#fff5fa"))
                elif isinstance(child,ctk.CTkFrame):
                    child.configure(fg_color=("#fff0ed","#25212b"))
                style(child)
        style(self)

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
