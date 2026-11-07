from pathlib import Path
p=Path(__file__).resolve().parents[1]/'outputs/rad_ai_v0.2.4/assistant/ui.py'
s=p.read_text()
s=s.replace('[("Bind current chat", self.bind_chat), ("Search for partner",', '[("Search for partner",')
s=s.replace('        ttk.Button(row, text="Watch current chat", command=self.watch).pack(side="left")\n','')
s=s.replace('        ttk.Button(row, text="1. Read screen", command=self.read).pack(side="left")\n','')
s=s.replace('        ttk.Button(row, text="2. Generate reply", command=self.generate).pack(side="left", padx=6)\n','')
s=s.replace('3. Send reviewed reply','Send reviewed reply')
s=s.replace('        root.after(100, self.poll)','        root.after(100, self.poll)\n        root.after(1200, self.auto_tick)',1)
# Platform changes cancel read/generation and wait for its worker to exit.
s=s.replace('        if self.busy or (self.conversation and self.conversation.uncertain):', '''        if self.busy and not (self.conversation and self.conversation.uncertain):
            self.cancel.set()
            if self.conversation:
                self.conversation.pause()
            self.root.after(200, self.select_platform)
            return
        if self.busy or (self.conversation and self.conversation.uncertain):''',1)
s=s.replace('        self.generated(reply)\n\n    def generated', '''        self.generated(reply)
        if self.auto_send.get():
            self.root.after(50, self.send)

    def generated''')
s=s.replace('                return driver.profile.get("auto_state", "unknown")','                state = driver.profile.get("auto_state", "unknown")\n                return state, driver.observe() if state == "chat" else None')
start=s.index('            def ready(state):')
end=s.index('            self.screen_task(scan, ready)',start)
s=s[:start]+'''            def ready(result):
                state, observed = result
                self.conversation, self.latest = None, None
                self.incoming.delete("1.0", "end")
                self.reply.delete("1.0", "end")
                if observed:
                    self.bound(observed)
                self.report(f"Ready: {state}. Incoming messages are read and drafted automatically.")
'''+s[end:]
pos=s.index('    def model_settings(self):')
s=s[:pos]+'''    def auto_tick(self):
        try:
            if not self.busy and not self.cancel.is_set() and self.driver and not (self.conversation and self.conversation.uncertain):
                # Do not repeatedly steal focus while the operator uses other apps.
                foreground = user32.GetForegroundWindow()
                if foreground in (self.driver.handle, user32.GetAncestor(self.root.winfo_id(), 2)):
                    self.screen_task(lambda driver: driver.observe(), self.auto_observed)
        finally:
            if not self.closed.is_set():
                self.root.after(1200, self.auto_tick)

    def auto_observed(self, observed):
        if not self.conversation or observed.identity != self.conversation.identity:
            self.bound(observed)
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

'''+s[pos:]
p.write_text(s)
