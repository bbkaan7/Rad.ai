"""Tk stays on the main thread; async networking runs on a dedicated loop."""

import asyncio
import queue
import threading
import os
from tkinter import messagebox
from pathlib import Path
from PIL import Image, ImageTk
from concurrent.futures import CancelledError
import customtkinter as ctk
from ayarlar import load, VERSION
from .engine import Engine
from .transcript import ConversationView
from .diagnostics import install, record, LOG_PATH


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
        install(self.loop)
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
        operation=getattr(getattr(coroutine,'cr_code',None),'co_name','worker_command')
        future=asyncio.run_coroutine_threadsafe(coroutine,self.loop)
        def done(result):
            try:
                result.result()
            except (CancelledError,asyncio.CancelledError):
                pass
            except Exception as error:
                record('gui.worker_command',error,operation=operation)
                self.events.put({"type":"status","text":f"{type(error).__name__}: {error}"})
        future.add_done_callback(done)
        return future


ASSETS = Path(__file__).resolve().parent.parent / "assets"


class Panel(ctk.CTk):
    def __init__(self):
        ctk.set_default_color_theme(str(ASSETS / "rad-theme.json"))
        super().__init__()
        self.title(f"Rad.ai v{VERSION}")
        self.geometry("1200x820")
        self.minsize(1100, 740)
        self.brand_images=[]
        self.install_icon()
        self.events=queue.Queue()
        self.chats={}
        self.buttons={}
        self.notification_buttons={}
        self.selected=None
        self.reply_to=None
        self.message_options={}
        self.drafts={}
        self.start_pending=False
        self.closing=False
        self.worker=Worker(load(),self.events)
        self.grid_columnconfigure(1,weight=1)
        self.grid_rowconfigure(1,weight=1)
        top=ctk.CTkFrame(self)
        top.grid(row=0,column=0,columnspan=2,sticky="ew",padx=12,pady=12)
        self.brand(top)
        ctk.CTkLabel(top,text=f"v{VERSION}",text_color=("#7D606C","#BCAAC6")).pack(side="left",padx=(0,12))
        self.auto=ctk.CTkSwitch(top,text="Auto-reply: OFF",command=self.toggle)
        self.auto.pack(side="right",padx=12)
        ctk.CTkButton(top,text="Connect Telegram (ADB)",command=lambda:self.connect("telegram")).pack(side="left",padx=4)
        self.start_anon_button=ctk.CTkButton(top,text="Start AnonChat",command=self.start_anon)
        self.start_anon_button.pack(side="left",padx=4)
        ctk.CTkButton(top,text='Android bridge',width=110,command=lambda:self.worker.submit(self.worker.engine.setup_android())).pack(side='left',padx=4)
        self.tabs=ctk.CTkTabview(self,width=260,command=self.platform_selected)
        self.tabs.grid(row=1,column=0,sticky="nsew",padx=(12,6))
        self.sections={}
        for platform in ("AnonChat","Telegram"):
            tab=self.tabs.add(platform)
            if platform=="AnonChat":
                ctk.CTkButton(tab,text="Link to Telegram",command=self.create_handoff).pack(fill="x",pady=3)
            if platform=="Telegram":
                self.chat_search=ctk.CTkEntry(tab,placeholder_text="Existing chat name")
                self.chat_search.pack(fill="x",pady=3)
                ctk.CTkButton(tab,text="Open existing chat",command=self.open_telegram_chat).pack(fill="x",pady=3)
            platform_key="telegram" if platform=="Telegram" else "anonchat"
            ctk.CTkButton(tab,text="Stop monitoring",command=lambda p=platform_key:self.worker.submit(self.worker.engine.disconnect(p))).pack(fill="x",pady=3)
            decoration=ctk.CTkLabel(tab,text="🐾   ·   🐾   ·   🐾",font=("Segoe UI Symbol",20),text_color=("#C77599","#9E78B2"))
            decoration.pack(side="bottom",pady=10)
            if not hasattr(self,"paw_trails"):
                self.paw_trails=[]
            self.paw_trails.append(decoration)
            if not hasattr(self,'notification_sections'):self.notification_sections={}
            notices=ctk.CTkScrollableFrame(tab,height=95,label_text='Notification previews')
            notices.pack(side='bottom',fill='x',pady=4)
            self.notification_sections[platform]=notices
            sidebar=ctk.CTkScrollableFrame(tab)
            sidebar.pack(fill="both",expand=True)
            for category in (("New partner","Friends") if platform=="AnonChat" else ("Chats",)):
                section=ctk.CTkFrame(sidebar)
                section.pack(fill="x",pady=5)
                ctk.CTkLabel(section,text=category).pack(anchor="w",padx=8)
                self.sections[(platform,category)]=section
        right=ctk.CTkFrame(self)
        self.chat_panel=right
        right.grid(row=1,column=1,sticky="nsew",padx=(6,12))
        right.grid_columnconfigure(0,weight=1)
        right.grid_rowconfigure(1,weight=1)
        self.heading=ctk.CTkLabel(right,text="Select a conversation")
        self.heading.grid(row=0,column=0,sticky="w",padx=12,pady=8)
        self.feed=ConversationView(right)
        self.feed.grid(row=1,column=0,sticky="nsew",padx=12,pady=4)
        controls=ctk.CTkFrame(right)
        controls.grid(row=2,column=0,sticky="ew",padx=12,pady=4)
        ctk.CTkButton(controls,text="Start cycle",width=100,command=self.start_cycle).pack(side="left",padx=3)
        ctk.CTkButton(controls,text="Resume selected",width=110,command=self.resume).pack(side="left",padx=3)
        for label,action in (("Search partner","search"),("Next partner","next"),("End chat","end")):
            ctk.CTkButton(controls,text=label,width=100,command=lambda a=action:self.match_anon(a)).pack(side="left",padx=3)
        ctk.CTkButton(controls,text="Check send",width=100,command=self.check_send).pack(side="left",padx=3)
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
        footer=ctk.CTkFrame(self,fg_color="transparent")
        footer.grid(row=2,column=0,columnspan=2,sticky="ew",padx=12,pady=8)
        footer.grid_columnconfigure(0,weight=1)
        self.theme_mode="Dark"
        self.theme_toggle=ctk.CTkButton(footer,text="☾",width=42,height=38,font=("Segoe UI Symbol",26),fg_color="transparent",command=self.toggle_theme)
        self.theme_toggle.grid(row=0,column=2,sticky="e",padx=4)
        ctk.CTkButton(footer,text='Open error log',width=115,command=self.open_error_log).grid(row=0,column=1,padx=4)
        self.status=ctk.CTkLabel(footer,text="Connect a platform. Auto-reply is OFF.",anchor="w",wraplength=980)
        self.status.grid(row=0,column=0,sticky="ew",padx=4,pady=4)
        self.build_settings()
        self.protocol("WM_DELETE_WINDOW",self.close)
        self.set_theme("Dark")
        self.platform_selected()
        self.after(60,self.poll)

    def connect(self,platform):
        self.tabs.set("Telegram" if platform=="telegram" else "AnonChat")
        self.platform_selected()
        self.worker.submit(self.worker.engine.connect(platform))

    def build_settings(self):
        tab=self.tabs.add('Settings')
        ctk.CTkLabel(tab,text='Reply and connection settings',wraplength=220).pack(pady=15)
        panel=ctk.CTkScrollableFrame(self)
        panel.grid(row=1,column=1,sticky='nsew',padx=(6,12))
        panel.grid_columnconfigure(1,weight=1)
        self.settings_panel=panel
        self.setting_fields={}
        settings=self.worker.settings
        ctk.CTkLabel(panel,text='Settings',font=('Segoe UI',24,'bold')).grid(row=0,column=0,columnspan=2,sticky='w',padx=20,pady=20)
        for row,(name,label) in enumerate((('model','Ollama model'),('ollama_url','Ollama URL'),
            ('llm_timeout_seconds','LLM timeout (seconds)'),('debounce_seconds','Collect incoming messages (seconds)'),
            ('typing_delay_seconds','Start waiting draft after (seconds)'),('typing_interval_seconds','Waiting draft pace (seconds)')),1):
            ctk.CTkLabel(panel,text=label).grid(row=row,column=0,sticky='w',padx=20,pady=10)
            field=ctk.CTkEntry(panel,width=300)
            field.insert(0,str(getattr(settings,name)))
            field.grid(row=row,column=1,sticky='ew',padx=20,pady=10)
            self.setting_fields[name]=field
        for row,(name,label) in enumerate((('typing_enabled','Show typing while waiting for the LLM'),('anon_greeting','Send hii :3 for a new AnonChat match')),7):
            field=ctk.CTkSwitch(panel,text=label)
            if getattr(settings,name):field.select()
            field.grid(row=row,column=0,columnspan=2,sticky='w',padx=20,pady=12)
            self.setting_fields[name]=field
        ctk.CTkLabel(panel,text='Temporary typing text is never sent. Manually edited Android drafts are kept.',wraplength=620,justify='left').grid(row=9,column=0,columnspan=2,sticky='w',padx=20,pady=10)
        ctk.CTkButton(panel,text='Save settings',command=self.save_settings).grid(row=10,column=0,sticky='w',padx=20,pady=15)
        ctk.CTkLabel(panel,text=f'Android device: {settings.adb_device_host}:{settings.adb_device_port}\nAccessibility bridge: 127.0.0.1:{settings.accessibility_port}',justify='left').grid(row=11,column=0,columnspan=2,sticky='w',padx=20,pady=10)
        ctk.CTkButton(panel,text='Install / open Android bridge',command=lambda:self.worker.submit(self.worker.engine.setup_android())).grid(row=12,column=0,columnspan=2,sticky='w',padx=20,pady=10)
        ctk.CTkLabel(panel,text='Stop both monitors before updating the Android bridge. Enable its Android permissions manually if prompted.',wraplength=620,justify='left').grid(row=13,column=0,columnspan=2,sticky='w',padx=20,pady=10)
        panel.grid_remove()

    def save_settings(self):
        try:
            values={name:(bool(field.get()) if name in {'typing_enabled','anon_greeting'} else
                field.get().strip() if name in {'model','ollama_url'} else float(field.get()))
                for name,field in self.setting_fields.items()}
            from dataclasses import replace
            from ayarlar import validate
            validate(replace(self.worker.settings,**values))
        except ValueError as error:
            self.status.configure(text='Settings not saved: '+str(error));return
        self.worker.submit(self.worker.engine.update_settings(values))

    def open_error_log(self):
        from .diagnostics import configure
        path=configure()
        os.startfile(str(path))

    def open_telegram_chat(self):
        self.worker.submit(self.worker.engine.open_telegram_chat(self.chat_search.get()))

    def start_anon(self):
        if self.start_pending:
            return
        self.start_pending=True
        self.start_anon_button.configure(state="disabled",text="Starting...")
        self.status.configure(text="Starting AnonChat and finding a partner...")
        self.tabs.set("AnonChat")
        self.platform_selected()
        future=self.worker.submit(self.worker.engine.start_anon())
        # Completion callbacks run on the worker; only the main thread updates Tk.
        future.add_done_callback(lambda _:self.events.put({"type":"start_anon_done"}))

    def match_anon(self,action):
        self.tabs.set("AnonChat")
        self.platform_selected()
        self.worker.submit(self.worker.engine.match_anon(action))

    def toggle(self):
        self.worker.submit(self.worker.engine.set_auto(bool(self.auto.get())))

    def select(self,key):
        if key not in self.chats:
            return
        self.save_draft()
        self.tabs.set("Telegram" if key.startswith("telegram:") else "AnonChat")
        self.selected=key
        self.reply_to=None
        self.restore_draft()
        self.platform_selected()
        self.render()
        if key.startswith('anonchat:') and self.chats[key].get('category')=='Friends':
            self.worker.submit(self.worker.engine.open_friend(key))

    def save_draft(self):
        if self.selected:
            self.drafts[self.selected]=self.entry.get("1.0","end").rstrip("\n")

    def restore_draft(self):
        self.entry.delete("1.0","end")
        if self.selected:
            self.entry.insert("1.0",self.drafts.get(self.selected,""))

    def clear_conversation(self,title="Select a conversation"):
        self.selected=None
        self.reply_to=None
        self.message_options={}
        self.entry.delete("1.0","end")
        self.feed.set_messages([])
        self.heading.configure(text=title)
        self.message_picker.configure(values=["Select a message"])
        self.message_picker.set("Select a message")

    def render(self):
        if self.selected not in self.chats:
            return
        chat=self.chats[self.selected]
        state=" — uncertain send" if chat["uncertain"] else " — manual/paused" if chat["paused"] else ""
        if chat.get("closed"):
            state=" — Chat closed"
        elif chat.get("busy"):
            state=" - Typing..."
        if chat.get("linked"):
            state+=" · Linked identity"
        if self.reply_to:
            state+=f" - Reply to #{self.reply_to}"
        self.heading.configure(text=chat["title"]+state)
        previous=self.message_picker.get()
        self.message_options={f"#{m['id']} {m['role']}: {m['text'][:35]}":m for m in chat["messages"]}
        options=list(self.message_options) or ["Select a message"]
        self.message_picker.configure(values=options)
        self.message_picker.set(previous if previous in options else options[-1])
        self.feed.set_messages(chat["messages"])

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
            try:self.handle_event(event)
            except Exception as error:
                record('gui.event',error,operation=event.get('type','unknown'))
                self.status.configure(text='UI update failed. Details saved to runtime/rad_error.log.')
        if not self.closing:
            self.after(60,self.poll)

    def report_callback_exception(self,kind,error,tb):
        record('gui.callback',error.with_traceback(tb))
        if hasattr(self,'status'):
            self.status.configure(text='Action failed. Details saved to runtime/rad_error.log.')

    def handle_event(self,event):
        kind=event["type"]
        if kind=='settings_saved':
            self.worker.settings=event['settings']
        elif kind=="status":
            self.status.configure(text=event["text"])
        elif kind=='notification':
            ident=event['id']
            platform='AnonChat' if event['package']=='io.anonchat' else 'Telegram'
            if ident not in self.notification_buttons:
                widget=ctk.CTkLabel(self.notification_sections[platform],anchor='w',justify='left',wraplength=200)
                widget.pack(fill='x',pady=3)
                self.notification_buttons[ident]=widget
            self.notification_buttons[ident].configure(text=event['title']+' — awaiting verification\n'+event['text'][:250])
            while len(self.notification_buttons)>100:
                first=next(iter(self.notification_buttons));self.notification_buttons.pop(first).destroy()
        elif kind=='notification_verified':
            widget=self.notification_buttons.pop(event['id'],None)
            if widget:widget.destroy()
        elif kind=="auto":
            self.auto.select() if event["value"] else self.auto.deselect()
            self.auto.configure(text="Auto-reply: ON" if event["value"] else "Auto-reply: OFF")
        elif kind=="start_anon_done":
            self.start_pending=False
            self.start_anon_button.configure(state="normal",text="Start AnonChat")
        elif kind=="chat_removed":
            key=event["key"]
            self.chats.pop(key,None)
            self.drafts.pop(key,None)
            button=self.buttons.pop(key,None)
            if button is not None:
                button.destroy()
            if self.selected==key:
                self.clear_conversation("Chat closed")
                self.status.configure(text="Chat closed. Temporary conversation removed.")
        elif kind=="chat":
            key=event["key"]
            if self.chats.get(key)==event:
                return
            self.chats[key]=event
            platform="Telegram" if key.startswith("telegram:") else "AnonChat"
            category="Friends" if event.get("category")=="Friends" else "New partner"
            section=self.sections[(platform,category if platform=="AnonChat" else "Chats")]
            old=self.buttons.get(key)
            if old and old.master!=section:
                old.destroy()
                self.buttons.pop(key)
            if key not in self.buttons:
                button=ctk.CTkButton(section,text=event["title"],command=lambda k=key:self.select(k))
                button.pack(fill="x",pady=4,padx=4)
                self.buttons[key]=button
            self.buttons[key].configure(text=event["title"]+(" - Chat closed" if event.get("closed") else " - Typing..." if event.get("busy") else ""))
            # Background platform updates must never steal the selected conversation.
            if self.selected is None and self.tabs.get()==platform:
                self.selected=key
                self.reply_to=None
                self.restore_draft()
            if self.selected==key:
                self.render()
        elif kind=="select_chat":
            self.select(event["key"])
        elif kind=="handoff":
            messagebox.showinfo("Link to Telegram",f"Ask this person to send this code alone in Telegram:\n\n{event['code']}\n\nValid once, for 10 minutes. No message has been sent.",parent=self)
        elif kind=="manual_done":
            key=event["key"]
            if self.drafts.get(key,"").strip()==event["text"]:
                self.drafts.pop(key,None)
            if self.selected==key and self.entry.get("1.0","end").strip()==event["text"]:
                self.entry.delete("1.0","end")
                self.reply_to=None
                self.render()

    def start_cycle(self):
        if self.selected:
            self.worker.submit(self.worker.engine.start_cycle(self.selected))
        elif self.tabs.get()=="AnonChat":
            self.start_anon()

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

    def install_icon(self):
        icon=ASSETS / "rad-paw.png"
        if icon.exists():
            self.window_icon=ImageTk.PhotoImage(Image.open(icon),master=self)
            self.iconphoto(True,self.window_icon)
            ico=ASSETS / "rad-paw.ico"
            if ico.exists():
                self.after(250,lambda:self.iconbitmap(str(ico)))

    def brand(self,parent):
        path=ASSETS / "rad-logo.png"
        if path.exists():
            image=Image.open(path)
            height=64
            width=round(image.width*height/image.height)
            logo=ctk.CTkImage(light_image=image,dark_image=image,size=(width,height))
            self.brand_images.append(logo)
            ctk.CTkLabel(parent,text="",image=logo).pack(side="left",padx=12,pady=8)
        else:
            ctk.CTkLabel(parent,text="Rad.ai",font=("Segoe UI",24,"bold")).pack(side="left",padx=12)

    def check_send(self):
        if self.selected:
            self.worker.submit(self.worker.engine.reconcile(self.selected))

    def create_handoff(self):
        if self.selected:
            self.worker.submit(self.worker.engine.create_handoff(self.selected))

    def platform_selected(self):
        if self.tabs.get()=='Settings':
            self.chat_panel.grid_remove();self.settings_panel.grid()
            return
        self.settings_panel.grid_remove();self.chat_panel.grid()
        platform="telegram" if self.tabs.get()=="Telegram" else "anonchat"
        self.worker.submit(self.worker.engine.select_platform(platform))
        if self.selected is None or not self.selected.startswith(platform+":"):
            self.save_draft()
            self.selected=next((key for key in self.chats if key.startswith(platform+":")),None)
            self.reply_to=None
            self.restore_draft()
            if self.selected:
                self.render()
            else:
                self.clear_conversation()

    def toggle_theme(self):
        self.set_theme("Light" if self.theme_mode=="Dark" else "Dark")

    def set_theme(self,value):
        # Every widget uses the same paired palette, including dynamic chat buttons.
        self.theme_mode=value
        self.theme_toggle.configure(text="☀" if value=="Light" else "☾")
        ctk.set_appearance_mode(value.lower())
        for trail in self.paw_trails:
            trail.configure(text="🐾   ·   🐾   ·   🐾" if value=="Light" else "🐾")

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
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Rad.ai.Desktop")
    except (AttributeError,OSError):
        pass
    Panel().mainloop()
