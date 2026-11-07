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
from .flow import prepare_current, deliver_parts
from .opening import OpeningGate, open_match
from .desktop import Desktop, user32, crop
from .model import Ollama
from .diagnostics import check_installation



class Panel:
    def __init__(self, root):
        self.root = root
        self.cfg = config.load()
        self.cancel = threading.Event()
        self.events = queue.Queue()
        self.busy = False
        self.driver = None
        self.opening_gate = OpeningGate()
        self.sent_groups = 0
        self.conversation = None
        self.platform = tk.StringVar(value=self.cfg.get("last_platform", "telegram"))
        self.title = tk.StringVar()
        self.status = tk.StringVar(value="Setup required. No automatic messages are sent.")
        self.auto_send = tk.BooleanVar(value=False)
        root.title(f"Rad.ai v{VERSION}")
        root.geometry("820x880")
        body = ttk.Frame(root, padding=12)
        body.pack(fill="both", expand=True)
        # Display the supplied artwork as a small paw crop without modifying it.
        logo = Image.open(config.ROOT / "assets" / "rad-logo.jpg")
        paw = logo.crop((302, 224, 565, 481)).resize((42, 42), Image.Resampling.LANCZOS)
        self.paw_image = ImageTk.PhotoImage(paw)
        root.iconphoto(True, self.paw_image)
        brand = ttk.Frame(body)
        brand.pack(fill="x", pady=(0, 8))
        ttk.Label(brand, image=self.paw_image).pack(side="left")
        ttk.Label(brand, text="Rad.ai", font=("Segoe UI", 16, "bold")).pack(side="left", padx=8)
        ttk.Label(brand, text=f"v{VERSION} | Automatic calibration").pack(side="right")
        top = ttk.Frame(body)
        top.pack(fill="x")
        ttk.Label(top, text="Platform").pack(side="left")
        selector = ttk.Combobox(top, textvariable=self.platform, values=("anonchat", "telegram"), state="readonly", width=14)
        selector.pack(side="left", padx=8)
        selector.bind("<<ComboboxSelected>>", self.select_platform)
        ttk.Button(top, text="Pause / Take over (F10)", command=self.pause).pack(side="right")
        ttk.Button(top, text="Restart", command=self.restart).pack(side="right", padx=6)
        ttk.Label(body, text="Window filter (optional; leave blank to detect the application automatically)").pack(anchor="w", pady=(12, 2))
        ttk.Entry(body, textvariable=self.title).pack(fill="x")
        row = ttk.Frame(body)
        row.pack(fill="x", pady=8)
        ttk.Label(row, text="Calibration runs when you select a platform").pack(side="left", padx=8)
        ttk.Button(row, text="Model settings", command=self.model_settings).pack(side="right")
        ttk.Button(row, text="Check setup", command=lambda: self.guarded(lambda: self.task(lambda: check_installation(self.cfg), self.report))).pack(side="right", padx=4)
        row = ttk.Frame(body)
        row.pack(fill="x", pady=4)
        for title, command in [("Search for partner", lambda: self.match("search")), ("Next partner", lambda: self.match("next"))]:
            ttk.Button(row, text=title, command=command).pack(side="left", padx=(0, 5))
        row = ttk.Frame(body)
        row.pack(fill="x", pady=5)
        ttk.Checkbutton(row, text="Experimental auto-send (current chat only, max 10 replies)", variable=self.auto_send).pack(side="left", padx=8)
        ttk.Label(body, text="Anonchat: new matches receive hii :3 and a bio opener automatically.").pack(anchor="w")
        ttk.Label(body, text="Incoming text (check OCR before generating)").pack(anchor="w", pady=(10, 2))
        self.incoming = tk.Text(body, height=5, wrap="word")
        self.incoming.pack(fill="x")
        row = ttk.Frame(body)
        row.pack(fill="x", pady=6)
        ttk.Button(row, text="Rewrite reply", command=self.rewrite).pack(side="left")
        ttk.Label(body, text="Reply draft (editable)").pack(anchor="w")
        self.reply = tk.Text(body, height=5, wrap="word")
        self.reply.pack(fill="x")
        row = ttk.Frame(body)
        row.pack(fill="x", pady=6)
        ttk.Button(row, text="Send reviewed reply", command=self.send).pack(side="left")
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
        root.after(1200, self.auto_tick)

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
        if self.busy and not (self.conversation and self.conversation.uncertain):
            self.cancel.set()
            if self.conversation:
                self.conversation.pause()
            self.root.after(200, self.select_platform)
            return
        if self.busy or (self.conversation and self.conversation.uncertain):
            if self.conversation:
                self.platform.set(self.conversation.platform)
            else:
                self.platform.set(getattr(self, "selected_platform", "telegram"))
            self.report("Finish the operation and resolve any pending send before switching.")
            return
        self.opening_gate = OpeningGate()
        self.selected_platform = self.platform.get()
        self.cfg = config.load()
        self.cfg["last_platform"] = self.selected_platform
        config.save(self.cfg)
        self.conversation = None
        self.latest = None
        self.title.set(self.cfg["profiles"][self.platform.get()]["window_title"])
        self.incoming.delete("1.0", "end")
        self.reply.delete("1.0", "end")
        self.driver = None
        self.sent_groups = 0
        self.calibrate()

    def task(self, operation, done, quiet=False):
        self.require_idle()
        self.busy = True
        self.cancel.clear()
        if not quiet:
            self.report("Working... F10 pauses screen actions immediately.")

        def worker():
            try:
                value = operation()
                self.events.put((done, value, None))
            except Exception as error:
                self.events.put((done, None, str(error)))

        threading.Thread(target=worker, daemon=True).start()

    def screen_task(self, action, done, quiet=False):
        profile = copy.deepcopy(self.profile())

        def operation():
            driver = self.driver
            if driver is None or driver.profile.get("window_title") != profile.get("window_title"):
                driver = Desktop(profile, self.cfg, self.cancel)
                self.driver = driver
            driver.focus()
            return action(driver)

        self.task(operation, done, quiet=quiet)

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
        if self.opening_gate.claim(self.platform.get()):
            session = self.conversation
            self.screen_task(lambda driver: open_match(session, driver, Ollama(self.cfg)), self.report)
            return True
        return False

    def read(self):
        self.guarded(lambda: self.screen_task(lambda d: d.observe(), self.read_done))

    def read_done(self, observation):
        self.latest = observation
        self.incoming.delete("1.0", "end")
        self.incoming.insert("1.0", observation.incoming)
        self.reply.delete("1.0", "end")
        self.report("Screen read. Consecutive incoming messages are grouped in order.")

    def generate(self):
        def start():
            if not self.conversation or not self.latest:
                raise ValueError("Bind the chat and read the incoming message first.")
            if self.incoming.get("1.0", "end").strip() != self.latest.incoming:
                raise ValueError("OCR edits are not supported yet. Select the platform again and read the message.")
            if self.cancel.is_set():
                self.report("Resuming with a new draft; no send is automatic.")
            self.conversation.paused = False
            session, observed = self.conversation, self.latest
            self.screen_task(lambda driver: prepare_current(session, driver.observe(),
                Ollama(self.cfg), driver.observe, driver.check), self.group_generated)
        self.guarded(start)

    def group_generated(self, result):
        observed, reply = result
        self.latest = observed
        self.incoming.delete("1.0", "end")
        self.incoming.insert("1.0", observed.incoming)
        self.generated(reply)
        if self.auto_send.get():
            self.root.after(50, self.send)

    def generated(self, reply):
        self.reply.delete("1.0", "end")
        self.reply.insert("1.0", reply)
        self.report("Draft ready. [NEXT_MESSAGE] separates outgoing bubbles. Review before sending.")

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
                if session.pending and observation.identity == session.identity and observation.incoming != session.pending.incoming:
                    return ("updated", prepare_current(session, observation, Ollama(self.cfg), driver.observe, driver.check))
                return ("sent", deliver_parts(session, driver, observation, reply))

            def done(result):
                kind, value = result
                if kind == "updated":
                    self.group_generated(value)
                    self.report("New messages included. Review the updated draft before sending.")
                else:
                    self.report(value)
                    if not session.uncertain:
                        self.reply.delete("1.0", "end")
                        self.sent_groups += 1
                        if self.sent_groups >= 10:
                            self.auto_send.set(False)
                            self.report("Automatic sending stopped after 10 reply groups. Drafting remains active.")
            self.screen_task(action, done)
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
            self.opening_gate.search_started()
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
            if send_enabled and profile.get("outgoing_color") is None and not profile.get("auto_calibration"):
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
                    fresh, reply = prepare_current(session, observed, model, driver.observe, driver.check)
                    session.validate_send(fresh, reply)
                    if not send_enabled:
                        return (fresh, reply)
                    deliver_parts(session, driver, fresh, reply)
                    if session.uncertain:
                        raise ValueError("Unable to verify submission. Reconcile the pending message.")
                    count += 1
                    if count >= 10:
                        return ""
                raise InterruptedError("Watch paused.")

            self.screen_task(run, lambda reply: self.group_generated(reply) if reply else self.report("Watch stopped after 10 replies. Review the conversation before restarting."))
        self.guarded(start)

    def calibrate(self):
        def start():
            if self.conversation and self.conversation.uncertain:
                raise ValueError("Resolve the pending send before rescanning the screen.")
            def scan(driver):
                driver.capture()
                state = driver.profile.get("auto_state", "unknown")
                return state, driver.observe() if state == "chat" else None
            def ready(result):
                state, observed = result
                self.conversation, self.latest = None, None
                self.incoming.delete("1.0", "end")
                self.reply.delete("1.0", "end")
                if not observed and self.platform.get() == "anonchat":
                    self.opening_gate.waiting_screen()
                if observed:
                    self.bound(observed)
                self.report(f"Ready: {state}. Incoming messages are read and drafted automatically.")
            self.screen_task(scan, ready)
        self.guarded(start)

    def auto_tick(self):
        try:
            if not self.busy and not self.cancel.is_set() and self.driver and time.monotonic() >= getattr(self, "retry_after", 0) and not (self.conversation and self.conversation.uncertain):
                # Do not repeatedly steal focus while the operator uses other apps.
                foreground = user32.GetForegroundWindow()
                if foreground == self.driver.handle:
                    self.screen_task(self.observe_available, self.auto_observed, quiet=True)
        finally:
            if not self.closed.is_set():
                self.root.after(700 if self.conversation else 500, self.auto_tick)

    def observe_available(self, driver):
        try:
            return driver.observe()
        except ValueError as error:
            if "No active chat detected" in str(error):
                return None
            raise

    def auto_observed(self, observed):
        if observed is None:
            if self.platform.get() == "anonchat":
                self.opening_gate.waiting_screen()
            self.conversation, self.latest = None, None
            self.incoming.delete("1.0", "end")
            self.reply.delete("1.0", "end")
            self.report("Waiting for an active conversation.")
            return
        if not self.conversation or observed.identity != self.conversation.identity:
            if self.bound(observed):
                return
        session = self.conversation
        self.latest = observed
        self.incoming.delete("1.0", "end")
        self.incoming.insert("1.0", observed.incoming)
        if not observed.incoming or observed.incoming == session.last_handled:
            return
        if session.pending and session.pending.incoming == observed.incoming:
            return
        session.paused = False
        self.screen_task(lambda driver: prepare_current(session, observed, Ollama(self.cfg),
            driver.observe, driver.check), self.group_generated)

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
                    self.retry_after = time.monotonic() + 15
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
