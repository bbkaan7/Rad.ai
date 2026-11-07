from pathlib import Path
root=Path(__file__).resolve().parents[1]/'outputs/rad_ai_v0.2.6'
p=root/'assistant/ui.py'
s=p.read_text()
s=s.replace('from .flow import prepare_current, deliver_parts','from .flow import prepare_current, deliver_parts\nfrom .opening import OpeningGate, open_match')
s=s.replace('        self.driver = None\n', '        self.driver = None\n        self.opening_gate = OpeningGate()\n',1)
s=s.replace('        ttk.Button(row, text="Draft greeting", command=self.greeting).pack(side="left", padx=6)\n','')
s=s.replace('        self.auto_send = tk.BooleanVar(value=False)','        self.auto_send = tk.BooleanVar(value=False)')
s=s.replace('        ttk.Label(body, text="Incoming text (check OCR before generating)")','        ttk.Label(body, text="Anonchat: new matches receive hii :3 and a bio opener automatically.").pack(anchor="w")\n        ttk.Label(body, text="Incoming text (check OCR before generating)")')
start=s.index('    def greeting(self):')
end=s.index('    def rewrite(self):',start)
s=s[:start]+s[end:]
s=s.replace('        self.report("New temporary conversation bound. Previous context is not reused.")', '''        self.report("New temporary conversation bound. Previous context is not reused.")
        if self.opening_gate.claim(self.platform.get()):
            session = self.conversation
            self.screen_task(lambda driver: open_match(session, driver, Ollama(self.cfg)), self.report)
            return True
        return False''')
s=s.replace('            self.conversation, self.latest = None, None\n            def search(driver):', '            self.conversation, self.latest = None, None\n            self.opening_gate.search_started()\n            def search(driver):')
s=s.replace('                if observed:\n                    self.bound(observed)', '                if not observed and self.platform.get() == "anonchat":\n                    self.opening_gate.waiting_screen()\n                if observed:\n                    self.bound(observed)')
s=s.replace('                self.root.after(1200 if self.conversation else 3000, self.auto_tick)','                self.root.after(700 if self.conversation else 500, self.auto_tick)')
s=s.replace('        if observed is None:\n            self.conversation', '        if observed is None:\n            if self.platform.get() == "anonchat":\n                self.opening_gate.waiting_screen()\n            self.conversation')
s=s.replace('            self.bound(observed)\n        session = self.conversation','            if self.bound(observed):\n                return\n        session = self.conversation')
# A platform switch must not carry an Anonchat match trigger into a later session.
s=s.replace('        self.selected_platform = self.platform.get()', '        self.opening_gate = OpeningGate()\n        self.selected_platform = self.platform.get()')
p.write_text(s)
(root/'VERSION').write_text('0.2.6\n')
p=root/'assistant/__init__.py'
p.write_text(p.read_text().replace('0.2.4','0.2.6'))
for name in ('README.md','RELEASE_NOTES.md'):
    p=root/name
    p.write_text(p.read_text().replace('v0.2.4','v0.2.6'))
