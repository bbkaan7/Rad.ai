from pathlib import Path
root=Path(__file__).resolve().parent.parent/'outputs/rad_ai_v0.2.4'
path=root/'assistant/ui.py'
s=path.read_text(encoding='utf-8')
start=s.index('FIELDS = ')
end=s.index('\n\nclass Panel:',start)
s=s[:start]+s[end:]
s=s.replace('from .vision import dominant_color\n','').replace('from .layout import calibration_profile, reference_region\n','')
s=s.replace('        self.field = tk.StringVar(value="incoming")\n','')
s=s.replace('root.title(f"Desktop Assistant {VERSION}")','root.title(f"Rad.ai v{VERSION}")')
s=s.replace('        root.geometry("780x820")','        root.geometry("820x880")')
s=s.replace('        top = ttk.Frame(body)', '''        # Display the supplied artwork as a small paw crop without modifying it.
        logo = Image.open(config.ROOT / "assets" / "rad-logo.jpg")
        paw = logo.crop((302, 224, 565, 481)).resize((42, 42), Image.Resampling.LANCZOS)
        self.paw_image = ImageTk.PhotoImage(paw)
        root.iconphoto(True, self.paw_image)
        brand = ttk.Frame(body)
        brand.pack(fill="x", pady=(0, 8))
        ttk.Label(brand, image=self.paw_image).pack(side="left")
        ttk.Label(brand, text="Rad.ai", font=("Segoe UI", 16, "bold")).pack(side="left", padx=8)
        ttk.Label(brand, text=f"v{VERSION} | Automatic calibration").pack(side="right")
        top = ttk.Frame(body)''',1)
s=s.replace('Window title filter (leave blank for Telegram; application process is checked)', 'Window filter (optional; leave blank to detect the application automatically)')
s=s.replace('        ttk.Combobox(row, textvariable=self.field, values=FIELDS, state="readonly", width=20).pack(side="left")\n        ttk.Button(row, text="Calibrate selected item", command=self.calibrate).pack(side="left", padx=6)', '        ttk.Button(row, text="Auto-calibrate", command=self.calibrate).pack(side="left")\n        ttk.Label(row, text="Runs automatically before screen actions").pack(side="left", padx=8)')
start=s.index('    def calibrate(self):')
end=s.index('    def model_settings(self):',start)
s=s[:start]+'''    def calibrate(self):
        def start():
            if self.conversation and self.conversation.uncertain:
                raise ValueError("Resolve the pending send before rescanning the screen.")
            def scan(driver):
                driver.capture()
                return driver.profile.get("auto_state", "unknown")
            def ready(state):
                self.conversation, self.latest = None, None
                self.incoming.delete("1.0", "end")
                self.reply.delete("1.0", "end")
                self.report(f"Automatic calibration complete: {state}. No manual selection needed. Bind the chat to continue.")
            self.screen_task(scan, ready)
        self.guarded(start)

'''+s[end:]
s=s.replace('if send_enabled and profile.get("outgoing_color") is None:', 'if send_enabled and profile.get("outgoing_color") is None and not profile.get("auto_calibration"):')
s=s.replace('Recalibrate and read the correct region.', 'Run Auto-calibrate and read the message again.')
path.write_text(s,encoding='utf-8')
path=root/'main.py'
s=path.read_text().replace('Start the supervised v0.2.0 development build.','Start Rad.ai.').replace('Desktop Assistant','Rad.ai')
path.write_text(s,encoding='utf-8')
(root/'assistant/__init__.py').write_text('"""Rad.ai desktop conversation assistant."""\n\nVERSION = "0.2.4"\n',encoding='utf-8')
(root/'VERSION').write_text('0.2.4\n',encoding='utf-8')
