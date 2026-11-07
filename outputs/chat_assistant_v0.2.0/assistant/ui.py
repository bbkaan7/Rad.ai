"""English operator panel with visual calibration and explicit draft review."""

import queue
import copy
import threading
import time
import subprocess
import sys
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import cv2
import keyboard
from PIL import Image, ImageTk

from . import VERSION
from . import config
from .core import Conversation
from .desktop import Desktop, user32, crop
from .model import Ollama
from .diagnostics import check_installation
from .vision import dominant_color
from .layout import calibration_profile, reference_region

FIELDS = ("chat", "incoming_sample", "outgoing_sample", "identity", "chat_anchor", "empty_textbox", "send", "search", "next", "searching", "ended", "blocked", "incoming")
HELP = {
    "chat_anchor": "Select a stable input-row icon visible only in an active chat, such as the camera or attachment icon.",
    "chat": "Select the message pane. Exclude the header, input, chat list and advertisements.",
    "incoming_sample": "Select one INCOMING bubble including its background. This enables moving-bubble detection.",
    "outgoing_sample": "Select one OUTGOING bubble including its background to verify submission.",
    "searching": "Select distinctive static content visible only while searching for a partner.",
    "ended": "Select distinctive content visible only when the current conversation has ended.",
    "blocked": "Select distinctive content visible only on a login or restriction screen.",
    "incoming": "Select ONLY the latest incoming message. Exclude outgoing messages and timestamps.",
    "identity": "Select the stable recipient name or unique chat ID. Exclude online status and animations.",
    "empty_textbox": "Select the entire EMPTY message input, including its placeholder and border.",
    "send": "Select a distinctive Send button. It may only appear after you manually enter a draft.",
    "search": "Select the Search for partner button on the Anonchat home screen.",
    "next": "Select the Next partner button. Do not include adjacent buttons.",
}


class Panel:
    def __init__(self, root):
        self.root = root
        self.cfg = config.load()
        self.cancel = threading.Event()
        self.events = queue.Queue()
        self.busy = False
        self.conversation = None
        self.platform = tk.StringVar(value=self.cfg.get("last_platform", "telegram"))
        self.title = tk.StringVar()
        self.field = tk.StringVar(value="incoming")
        self.status = tk.StringVar(value="Setup required. No automatic messages are sent.")
        self.auto_send = tk.BooleanVar(value=False)
        root.title(f"Desktop Assistant {VERSION}")
        root.geometry("780x820")
        body = ttk.Frame(root, padding=12)
        body.pack(fill="both", expand=True)
        top = ttk.Frame(body)
        top.pack(fill="x")
        ttk.Label(top, text="Platform").pack(side="left")
        selector = ttk.Combobox(top, textvariable=self.platform, values=("anonchat", "telegram"), state="readonly", width=14)
        selector.pack(side="left", padx=8)
        selector.bind("<<ComboboxSelected>>", self.select_platform)
        ttk.Button(top, text="Pause / Take over (F10)", command=self.pause).pack(side="right")
        ttk.Button(top, text="Restart", command=self.restart).pack(side="right", padx=6)
        ttk.Label(body, text="Window title filter (leave blank for Telegram; application process is checked)").pack(anchor="w", pady=(12, 2))
        ttk.Entry(body, textvariable=self.title).pack(fill="x")
        row = ttk.Frame(body)
        row.pack(fill="x", pady=8)
        ttk.Combobox(row, textvariable=self.field, values=FIELDS, state="readonly", width=20).pack(side="left")
        ttk.Button(row, text="Calibrate selected item", command=self.calibrate).pack(side="left", padx=6)
        ttk.Button(row, text="Model settings", command=self.model_settings).pack(side="right")
        ttk.Button(row, text="Check setup", command=lambda: self.guarded(lambda: self.task(lambda: check_installation(self.cfg), self.report))).pack(side="right", padx=4)
        row = ttk.Frame(body)
        row.pack(fill="x", pady=4)
        for title, command in [("Bind current chat", self.bind_chat), ("Search for partner", lambda: self.match("search")), ("Next partner", lambda: self.match("next"))]:
            ttk.Button(row, text=title, command=command).pack(side="left", padx=(0, 5))
        row = ttk.Frame(body)
        row.pack(fill="x", pady=5)
        ttk.Button(row, text="Watch current chat", command=self.watch).pack(side="left")
        ttk.Checkbutton(row, text="Experimental auto-send (current chat only, max 10 replies)", variable=self.auto_send).pack(side="left", padx=8)
        ttk.Label(body, text="Incoming text (check OCR before generating)").pack(anchor="w", pady=(10, 2))
        self.incoming = tk.Text(body, height=5, wrap="word")
        self.incoming.pack(fill="x")
        row = ttk.Frame(body)
        row.pack(fill="x", pady=6)
        ttk.Button(row, text="1. Read screen", command=self.read).pack(side="left")
        ttk.Button(row, text="2. Generate reply", command=self.generate).pack(side="left", padx=6)
        ttk.Button(row, text="Rewrite reply", command=self.rewrite).pack(side="left")
        ttk.Button(row, text="Draft greeting", command=self.greeting).pack(side="left", padx=6)
        ttk.Label(body, text="Reply draft (editable)").pack(anchor="w")
        self.reply = tk.Text(body, height=5, wrap="word")
        self.reply.pack(fill="x")
        row = ttk.Frame(body)
        row.pack(fill="x", pady=6)
        ttk.Button(row, text="3. Send reviewed reply", command=self.send).pack(side="left")
        ttk.Button(row, text="Confirm delivered", command=lambda: self.resolve(True)).pack(side="left", padx=6)
        ttk.Button(row, text="Not sent / draft cleared", command=lambda: self.resolve(False)).pack(side="left")
        ttk.Button(row, text="Finish pending send", command=self.finish_pending).pack(side="left", padx=6)
        ttk.Label(body, textvariable=self.status, wraplength=690).pack(anchor="w", pady=8)
        self.log = tk.Text(body, height=6, wrap="word", state="disabled")
        self.log.pack(fill="both", expand=True)
        self.select_platform()
        self.latest = None
        self.closed = threading.Event()
        # The hook catches short taps that can fall between polling intervals.
        self.stop_hook = None
        try:
            self.stop_hook = keyboard.on_press_key("f10", lambda _: self.signal_pause())
        except Exception:
            self.report("F10 hook unavailable; using the polling fallback and Pause button.")
        threading.Thread(target=self.watch_stop, daemon=True).start()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(100, self.poll)

    def report(self, message):
        self.status.set(message)
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def require_idle(self):
        if self.busy:
            raise ValueError("An operation is running. Pause or wait for completion.")

    def profile(self):
        # Pick up calibration-file updates between operations, never mid-operation.
        self.cfg = config.load()
        profile = self.cfg["profiles"][self.platform.get()]
        profile["window_title"] = self.title.get().strip()
        self.cfg["last_platform"] = self.platform.get()
        config.save(self.cfg)
        return profile

    def select_platform(self, _=None):
        if self.busy or (self.conversation and self.conversation.uncertain):
            if self.conversation:
                self.platform.set(self.conversation.platform)
            else:
                self.platform.set(getattr(self, "selected_platform", "telegram"))
            self.report("Finish the operation and resolve any pending send before switching.")
            return
        self.selected_platform = self.platform.get()
        self.cfg = config.load()
        self.cfg["last_platform"] = self.selected_platform
        config.save(self.cfg)
        self.conversation = None
        self.latest = None
        self.title.set(self.cfg["profiles"][self.platform.get()]["window_title"])
        self.incoming.delete("1.0", "end")
        self.reply.delete("1.0", "end")
        self.report("Platform selected. Bind the visible chat before replying.")

    def task(self, operation, done):
        self.require_idle()
        self.busy = True
        self.cancel.clear()
        self.report("Working... F10 pauses screen actions immediately.")

        def worker():
            try:
                value = operation()
                self.events.put((done, value, None))
            except Exception as error:
                self.events.put((done, None, str(error)))

        threading.Thread(target=worker, daemon=True).start()

    def screen_task(self, action, done):
        profile = copy.deepcopy(self.profile())

        def operation():
            driver = Desktop(profile, self.cfg, self.cancel)
            driver.focus()
            return action(driver)

        self.task(operation, done)

    def guarded(self, action):
        try:
            self.require_idle()
            action()
        except Exception as error:
            self.report(str(error))

    def bind_chat(self):
        def start():
            if self.conversation and self.conversation.uncertain:
                raise ValueError("Resolve the pending send before binding another chat.")
            self.screen_task(lambda d: d.observe(), self.bound)
        self.guarded(start)

    def bound(self, observation):
        self.conversation = Conversation(self.platform.get(), observation.identity)
        self.read_done(observation)
        self.report("New temporary conversation bound. Previous context is not reused.")

    def read(self):
        self.guarded(lambda: self.screen_task(lambda d: d.observe(), self.read_done))

    def read_done(self, observation):
        self.latest = observation
        self.incoming.delete("1.0", "end")
        self.incoming.insert("1.0", observation.incoming)
        self.reply.delete("1.0", "end")
        self.report("Screen read. Check that the text contains only the latest incoming message.")

    def generate(self):
        def start():
            if not self.conversation or not self.latest:
                raise ValueError("Bind the chat and read the incoming message first.")
            if self.incoming.get("1.0", "end").strip() != self.latest.incoming:
                raise ValueError("OCR edits are not supported yet. Recalibrate and read the correct region.")
            if self.cancel.is_set():
                self.report("Resuming with a new draft; no send is automatic.")
            self.conversation.paused = False
            session, observed = self.conversation, self.latest
            self.task(lambda: session.prepare(observed, Ollama(self.cfg)), self.generated)
        self.guarded(start)

    def generated(self, reply):
        self.reply.delete("1.0", "end")
        self.reply.insert("1.0", reply)
        self.report("Draft ready. Review it, then select Send reviewed reply.")

    def greeting(self):
        def start():
            if not self.conversation or not self.latest:
                raise ValueError("Bind the empty new chat first.")
            session, observed = self.conversation, self.latest
            session.paused = False
            self.task(lambda: session.prepare_greeting(observed, Ollama(self.cfg)), self.generated)
        self.guarded(start)

    def rewrite(self):
        def start():
            session = self.conversation
            draft = self.reply.get("1.0", "end").strip()
            if not session or not session.pending or session.uncertain or session.paused or not draft:
                raise ValueError("Generate an unsent draft first. Rewriting never sends a message.")
            instruction = simpledialog.askstring(
                "Rewrite reply", "How should the reply change?\nExamples: shorter, warmer, more direct.\nLeave blank for different wording.",
                parent=self.root,
            )
            if instruction is None:
                return
            self.task(lambda: session.rewrite(draft, instruction, Ollama(self.cfg)), self.generated)
        self.guarded(start)

    def send(self):
        def start():
            session = self.conversation
            if not session:
                raise ValueError("Bind a conversation first.")
            reply = self.reply.get("1.0", "end").strip()

            def action(driver):
                observation = driver.observe()
                session.begin_send(observation, reply)
                verified = driver.send(observation, session.draft)
                if verified:
                    session.resolve_send(True)
                return verified

            self.screen_task(action, lambda verified: self.report("Outgoing message observed; context updated. This does not prove server delivery." if verified else "Send action performed. Inspect the chat and confirm delivered or clear the unsent draft."))
        self.guarded(start)

    def resolve(self, delivered):
        def action():
            if not self.conversation:
                raise ValueError("No bound conversation.")
            self.conversation.resolve_send(delivered)
            self.reply.delete("1.0", "end")
            self.report("Send result recorded. Read the next incoming message to continue.")
        self.guarded(action)

    def finish_pending(self):
        def start():
            session = self.conversation
            if not session or not session.uncertain or not session.pending:
                raise ValueError("No pending send to finish. This action never types a second copy.")
            def action(driver):
                verified = driver.finish_pending(session.pending, session.draft)
                if verified:
                    session.resolve_send(True)
                return verified
            self.screen_task(action, lambda verified: self.report(
                "Outgoing message observed; context updated." if verified else
                "Submission attempted. Inspect the chat and reconcile the pending send."))
        self.guarded(start)

    def match(self, action):
        def start():
            if self.platform.get() != "anonchat":
                raise ValueError("Partner search is only available for Anonchat.")
            if self.conversation and self.conversation.uncertain:
                raise ValueError("Resolve the pending send before changing partners.")
            self.conversation, self.latest = None, None
            def search(driver):
                driver.search(action)
                if driver.wait_for_chat():
                    return driver.observe()
                return None
            self.screen_task(search, lambda observed: self.bound(observed) if observed else self.report("No chat detected within 30 seconds. Inspect the app; search was not repeated."))
        self.guarded(start)

    def watch(self):
        def start():
            session = self.conversation
            profile = self.profile()
            send_enabled = self.auto_send.get()
            if not session or session.uncertain:
                raise ValueError("Bind a chat and resolve any pending send before watching.")
            if profile.get("read_mode") != "bubbles":
                raise ValueError("Watch mode needs chat-pane and incoming-bubble calibration.")
            if send_enabled and profile.get("outgoing_color") is None:
                raise ValueError("Auto-send requires outgoing-bubble verification calibration.")
            if "chat_anchor" not in profile["templates"]:
                raise ValueError("Watch mode requires the active-chat anchor reference.")
            session.paused = False

            def run(driver):
                previous, stable_since, count = None, time.monotonic(), 0
                model = Ollama(self.cfg)
                while not self.cancel.wait(1):
                    observed = driver.observe()
                    if observed.identity != session.identity:
                        raise ValueError("The conversation changed. Watch stopped.")
                    if observed != previous:
                        previous, stable_since = observed, time.monotonic()
                        continue
                    if time.monotonic() - stable_since < 2 or not observed.incoming or observed.incoming == session.last_handled:
                        continue
                    reply = session.prepare(observed, model)
                    driver.check()
                    fresh = driver.observe()
                    session.validate_send(fresh, reply)
                    if not send_enabled:
                        return reply
                    session.begin_send(fresh, reply)
                    if not driver.send(fresh, reply):
                        raise ValueError("Unable to verify submission. Watch stopped; reconcile the send manually.")
                    session.resolve_send(True)
                    count += 1
                    if count >= 10:
                        return ""
                raise InterruptedError("Watch paused.")

            self.screen_task(run, lambda reply: self.generated(reply) if reply else self.report("Watch stopped after 10 replies. Review the conversation before restarting."))
        self.guarded(start)

    def calibrate(self):
        def start():
            if self.conversation and self.conversation.uncertain:
                raise ValueError("Resolve the pending send before changing calibration.")
            field = self.field.get()
            self.screen_task(lambda d: (d.capture(calibrated=False)[0], d.dpi), lambda result: self.select_region(result[0], field, result[1]))
        self.guarded(start)

    def select_region(self, frame, field, dpi):
        top = tk.Toplevel(self.root)
        top.title("Calibration: " + field)
        ttk.Label(top, text=HELP[field], wraplength=900).pack()
        scale = min(1, (self.root.winfo_screenwidth()-100)/frame.shape[1], (self.root.winfo_screenheight()-160)/frame.shape[0])
        image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        image = image.resize((int(image.width*scale), int(image.height*scale)))
        photo = ImageTk.PhotoImage(image)
        canvas = tk.Canvas(top, width=image.width, height=image.height, cursor="crosshair")
        canvas.pack()
        canvas.photo = photo
        canvas.create_image(0, 0, anchor="nw", image=photo)
        selection = {}

        def down(event):
            selection["start"] = (event.x, event.y)
            canvas.delete("selection")

        def drag(event):
            if "start" in selection:
                canvas.delete("selection")
                canvas.create_rectangle(*selection["start"], event.x, event.y, outline="red", width=2, tags="selection")

        def up(event):
            if "start" not in selection:
                return
            x, y = selection["start"]
            region = [int(min(x,event.x)/scale), int(min(y,event.y)/scale), int(abs(x-event.x)/scale), int(abs(y-event.y)/scale)]
            try:
                selected = crop(frame, region)
                size = [frame.shape[1], frame.shape[0]]
                profile, offset, layout_changed = calibration_profile(self.profile(), size, dpi)
                mapped_region = reference_region(region, offset, dpi, profile["reference_dpi"])
                if field in {"incoming", "identity", "chat"}:
                    profile["regions"][field] = mapped_region
                    if field == "incoming":
                        profile["read_mode"] = "region"
                elif field in {"incoming_sample", "outgoing_sample"}:
                    direction = field.split("_")[0]
                    profile[direction + "_color"] = dominant_color(selected)
                    profile[direction + "_tolerance"] = 2 if min(profile[direction + "_color"]) > 240 else 12
                    if direction == "incoming":
                        profile["read_mode"] = "bubbles"
                else:
                    if selected.std() < 2:
                        raise ValueError("Select a region containing visible detail.")
                    folder = config.ROOT / "templates" / self.platform.get()
                    folder.mkdir(parents=True, exist_ok=True)
                    path = folder / (field + ".png")
                    ok, encoded = cv2.imencode(".png", selected)
                    if not ok:
                        raise ValueError("Unable to encode reference image.")
                    encoded.tofile(path)
                    profile["templates"][field] = str(path.relative_to(config.ROOT))
                    profile.setdefault("template_dpi", {})[field] = dpi
                self.cfg["profiles"][self.platform.get()] = profile
                config.save(self.cfg)
                self.conversation, self.latest = None, None
                reset_note = " New layout: calibrate the remaining items." if layout_changed else ""
                self.report(f"Saved {field}. Rebind the chat after calibration." + reset_note)
                top.destroy()
            except Exception as error:
                messagebox.showerror("Calibration", str(error), parent=top)

        canvas.bind("<ButtonPress-1>", down)
        canvas.bind("<B1-Motion>", drag)
        canvas.bind("<ButtonRelease-1>", up)
        top.grab_set()

    def model_settings(self):
        def action():
            self.cfg = config.load()
            name = simpledialog.askstring("Local model", "Installed Ollama model name:", initialvalue=self.cfg["model"], parent=self.root)
            if name and name.strip():
                self.cfg["model"] = name.strip()
                config.save(self.cfg)
                self.report("Local model setting saved.")
        self.guarded(action)

    def pause(self):
        self.cancel.set()
        if self.conversation:
            self.conversation.pause()
        self.reply.delete("1.0", "end")
        self.report("Paused. Inspect any partially typed text. Model requests may take up to 90 seconds to finish.")

    def watch_stop(self):
        previous = False
        while not self.closed.wait(0.02):
            pressed = bool(user32.GetAsyncKeyState(0x79) & 0x8000)
            if pressed and not previous:
                self.signal_pause()
            previous = pressed

    def signal_pause(self):
        if not self.closed.is_set() and not self.cancel.is_set():
            self.cancel.set()
            self.events.put((None, None, "pause"))

    def poll(self):
        try:
            while True:
                done, value, error = self.events.get_nowait()
                if error == "pause":
                    self.pause()
                    continue
                self.busy = False
                if error:
                    self.report(error + (" Inspect the chat and resolve the pending send." if self.conversation and self.conversation.uncertain else ""))
                elif self.cancel.is_set():
                    self.report("Operation ended after pause. Result discarded; inspect any pending send.")
                else:
                    done(value)
        except queue.Empty:
            pass
        self.root.after(100, self.poll)

    def close(self):
        self.cancel.set()
        self.closed.set()
        if self.stop_hook is not None:
            self.stop_hook()
        self.root.destroy()

    def restart(self):
        def action():
            if self.conversation and self.conversation.uncertain:
                raise ValueError("Resolve the pending send before restarting.")
            subprocess.Popen([sys.executable, str(config.ROOT / "main.py")], cwd=config.ROOT,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.close()
        self.guarded(action)


def run():
    root = tk.Tk()
    Panel(root)
    root.mainloop()
