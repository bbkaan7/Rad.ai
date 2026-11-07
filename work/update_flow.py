from pathlib import Path
p=Path(__file__).resolve().parents[1]/'outputs/rad_ai_v0.2.4/assistant'
s=(p/'desktop.py').read_text()
s=s.replace('text = self.copy_bubble(frame, "incoming")','text = self.incoming_group(frame)')
s=s.replace('text = self.read_bubble(frame, "incoming")','text = self.incoming_group(frame)')
s=s.replace('def copy_bubble(self, frame, direction):','def copy_bubble(self, frame, direction, selected=None):')
s=s.replace('x, y, w, h = boxes[-1]','x, y, w, h = selected if selected is not None else boxes[-1]')
pos=s.index('    def ocr(self, image):')
s=s[:pos]+'''    def incoming_group(self, frame):
        region = self.message_region(frame)
        pane = crop(frame, region)
        if not self.profile.get("incoming_color"):
            self.profile.update(infer_colors(pane))
        incoming = self.profile.get("incoming_color")
        if incoming is None:
            return ""
        boxes = bubble_rectangles(pane, incoming, "left", self.profile.get("incoming_tolerance",12))
        outgoing = self.profile.get("outgoing_color")
        sent = bubble_rectangles(pane,outgoing,"right",self.profile.get("outgoing_tolerance",12)) if outgoing else []
        boundary = max((b[1]+b[3] for b in sent), default=0)
        boxes = [b for b in boxes if b[1] >= boundary]
        cache = getattr(self,"_bubble_text",{})
        messages = []
        for box in boxes:
            image = crop(pane,box)
            key = (image.shape, hashlib.sha256(image.tobytes()).digest())
            if key not in cache:
                text = (self.copy_bubble(frame,"incoming",selected=box)
                        if self.profile.get("text_source")=="clipboard" else self.ocr(image))
                cache[key] = strip_timestamp(text) if self.profile.get("timestamp_inside") else normalize(text)
            if cache[key]:
                messages.append(cache[key])
        self._bubble_text = cache if len(cache)<128 else {}
        return " [NEXT_INCOMING] ".join(messages)

'''+s[pos:]
# Avoid repeating expensive palette extraction once the layout learned colors.
s=s.replace('if self.profile.get("auto_calibration"):\n            pane', 'if self.profile.get("auto_calibration") and not self.profile.get(direction + "_color"):\n            pane')
s=s.replace('if self.profile.get("auto_calibration"):\n            self.profile.update(infer_colors(pane))','if self.profile.get("auto_calibration") and not self.profile.get(direction + "_color"):\n            self.profile.update(infer_colors(pane))')
(p/'desktop.py').write_text(s)
s=(p/'ui.py').read_text()
s=s.replace('from .core import Conversation','from .core import Conversation\nfrom .flow import prepare_current, deliver_parts')
s=s.replace('self.busy = False\n        self.conversation', 'self.busy = False\n        self.driver = None\n        self.conversation',1)
s=s.replace('        ttk.Button(row, text="Auto-calibrate", command=self.calibrate).pack(side="left")\n','')
s=s.replace('Runs automatically before screen actions','Calibration runs when you select a platform')
s=s.replace('        self.report("Platform selected. Bind the visible chat before replying.")','        self.driver = None\n        self.calibrate()')
s=s.replace('            driver = Desktop(profile, self.cfg, self.cancel)\n            driver.focus()', '''            driver = self.driver
            if driver is None or driver.profile.get("window_title") != profile.get("window_title"):
                driver = Desktop(profile, self.cfg, self.cancel)
                self.driver = driver
            driver.focus()''')
s=s.replace('Screen read. Check that the text contains only the latest incoming message.','Screen read. Consecutive incoming messages are grouped in order.')
s=s.replace('Run Auto-calibrate and read the message again.','Select the platform again and read the message.')
s=s.replace('            self.task(lambda: session.prepare(observed, Ollama(self.cfg)), self.generated)', '''            self.screen_task(lambda driver: prepare_current(session, driver.observe(),
                Ollama(self.cfg), driver.observe, driver.check), self.group_generated)''')
pos=s.index('    def generated(self, reply):')
s=s[:pos]+'''    def group_generated(self, result):
        observed, reply = result
        self.latest = observed
        self.incoming.delete("1.0", "end")
        self.incoming.insert("1.0", observed.incoming)
        self.generated(reply)

'''+s[pos:]
s=s.replace('Draft ready. Review it, then select Send reviewed reply.','Draft ready. [NEXT_MESSAGE] separates outgoing bubbles. Review before sending.')
start=s.index('                session.begin_send(observation, reply)')
end=s.index('\n        self.guarded(start)',start)
s=s[:start]+'''                if session.pending and observation.identity == session.identity and observation.incoming != session.pending.incoming:
                    return ("updated", prepare_current(session, observation, Ollama(self.cfg), driver.observe, driver.check))
                return ("sent", deliver_parts(session, driver, observation, reply))

            def done(result):
                kind, value = result
                if kind == "updated":
                    self.group_generated(value)
                    self.report("New messages included. Review the updated draft before sending.")
                else:
                    self.report(value)
            self.screen_task(action, done)'''+s[end:]
s=s.replace('                    reply = session.prepare(observed, model)\n                    driver.check()\n                    fresh = driver.observe()\n                    session.validate_send(fresh, reply)', '''                    fresh, reply = prepare_current(session, observed, model, driver.observe, driver.check)
                    session.validate_send(fresh, reply)''')
s=s.replace('                        return reply\n                    session.begin_send(fresh, reply)\n                    if not driver.send(fresh, reply):\n                        raise ValueError("Unable to verify submission. Watch stopped; reconcile the send manually.")\n                    session.resolve_send(True)', '''                        return (fresh, reply)
                    deliver_parts(session, driver, fresh, reply)
                    if session.uncertain:
                        raise ValueError("Unable to verify submission. Reconcile the pending message.")''')
s=s.replace('lambda reply: self.generated(reply) if reply else self.report("Watch stopped after 10 replies.', 'lambda reply: self.group_generated(reply) if reply else self.report("Watch stopped after 10 replies.')
(p/'ui.py').write_text(s)
