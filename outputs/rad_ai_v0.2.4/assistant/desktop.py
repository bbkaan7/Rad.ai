"""Windows screen adapter. Nothing runs until the operator requests an action."""

import ctypes
from ctypes import wintypes
import hashlib
import json
import os
import time

import cv2
import keyboard
import mss
import numpy as np
import pyautogui
import pyperclip
import pytesseract

from .config import ROOT
from .core import Observation, normalize
from .vision import bubble_rectangles, strip_timestamp, ocr_image
from .layout import content_offset
from .autocalibration import AutoCalibrator, CalibrationError, infer_colors

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.05
user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
user32.GetAncestor.restype = wintypes.HWND
user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.IsIconic.argtypes = [wintypes.HWND]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
user32.GetAsyncKeyState.restype = ctypes.c_short
user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
user32.GetDpiForWindow.argtypes = [wintypes.HWND]
user32.GetDpiForWindow.restype = wintypes.UINT
dwmapi = ctypes.WinDLL("dwmapi")
dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
ENUM = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = [ENUM, wintypes.LPARAM]
user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel32.CloseHandle.argtypes = [wintypes.HANDLE]


def window_process_name(handle):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
    process = kernel32.OpenProcess(0x1000, False, pid.value)
    if not process:
        return ""
    try:
        size = wintypes.DWORD(32768)
        text = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(process, 0, text, ctypes.byref(size)):
            return os.path.basename(text.value).casefold()
        return ""
    finally:
        kernel32.CloseHandle(process)


def same_process(first, second):
    first_pid, second_pid = wintypes.DWORD(), wintypes.DWORD()
    user32.GetWindowThreadProcessId(first, ctypes.byref(first_pid))
    user32.GetWindowThreadProcessId(second, ctypes.byref(second_pid))
    return first_pid.value != 0 and first_pid.value == second_pid.value


def target_window(title, process_name=""):
    if not title.strip() and not process_name:
        raise ValueError("Set a target window title or process name.")
    matches = []

    @ENUM
    def collect(handle, _):
        text = ctypes.create_unicode_buffer(user32.GetWindowTextLengthW(handle) + 1)
        user32.GetWindowTextW(handle, text, len(text))
        if (user32.IsWindowVisible(handle) and title.casefold() in text.value.casefold()
                and (not process_name or window_process_name(handle) == process_name.casefold())):
            matches.append(handle)
        return True

    user32.EnumWindows(collect, 0)
    if len(matches) != 1:
        raise ValueError(f"Expected one window containing '{title}'; found {len(matches)}.")
    handle = matches[0]
    if user32.IsIconic(handle):
        raise ValueError("Restore the target window first.")
    return handle


def bounds(handle):
    rect = wintypes.RECT()
    # Exclude Windows' invisible resize borders, matching the visible window capture.
    result = dwmapi.DwmGetWindowAttribute(handle, 9, ctypes.byref(rect), ctypes.sizeof(rect))
    if result != 0:
        if not user32.GetWindowRect(handle, ctypes.byref(rect)):
            raise ValueError("The target window is no longer available.")
    return {"left": rect.left, "top": rect.top,
            "width": rect.right - rect.left, "height": rect.bottom - rect.top}


def crop(frame, region):
    x, y, w, h = region
    if min(x, y) < 0 or min(w, h) < 4 or x + w > frame.shape[1] or y + h > frame.shape[0]:
        raise ValueError("Invalid screen region; recalibrate this profile.")
    return frame[y:y + h, x:x + w]


def locate(frame, template):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    if template is None or template.std() < 2:
        raise ValueError("Reference image is missing or has too little visual detail.")
    h, w = template.shape
    if h > gray.shape[0] or w > gray.shape[1]:
        raise ValueError("Reference image exceeds the target window.")
    scores = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
    _, confidence, _, point = cv2.minMaxLoc(scores)
    if not np.isfinite(confidence) or confidence < 0.90:
        raise ValueError("Element not found; no action performed.")
    # Reject distinct competing matches rather than selecting an arbitrary button.
    x, y = point
    scores[max(0, y-h//2):y+h//2+1, max(0, x-w//2):x+w//2+1] = -1
    if np.any(scores >= 0.90):
        raise ValueError("Multiple matching elements; use a more distinctive reference.")
    return x + w // 2, y + h // 2


class Desktop:
    def __init__(self, profile, config, cancelled):
        self.profile, self.config, self.cancelled = profile, config, cancelled
        self.handle = target_window(profile["window_title"], profile.get("process_name", ""))
        self.dpi = user32.GetDpiForWindow(self.handle) or 96
        self.scale = self.dpi / profile.get("reference_dpi", self.dpi)
        pytesseract.pytesseract.tesseract_cmd = config["tesseract"]

    def region(self, name):
        x, y, w, h = self.profile["regions"][name]
        left, top = round(x*self.scale), round(y*self.scale)
        return [left + getattr(self, "content_offset_x", 0), top,
                round((x+w)*self.scale)-left, round((y+h)*self.scale)-top]

    def find(self, frame, name):
        if self.profile.get("auto_calibration"):
            if getattr(self, "_matched_frame", None) is not frame:
                self._matched_frame, self._frame_matches = frame, {}
            if name in self._frame_matches:
                return self._frame_matches[name]
            area = list(self.profile.get("auto_viewport", [0,0,frame.shape[1],frame.shape[0]]))
            if name in {"chat_anchor", "empty_textbox", "send"}:
                cut = round(area[3]*0.45)
                area[1] += cut
                area[3] -= cut
            x,y,w,h = AutoCalibrator(self.profile).locate(frame,name,self.dpi,area)
            result = x+w//2,y+h//2
            self._frame_matches[name] = result
            return result
        offset = getattr(self, "content_offset_x", 0)
        x, y = locate(frame[:, offset:], self.template(name))
        return x + offset, y

    def check(self):
        if self.cancelled.is_set():
            raise InterruptedError("Paused by the operator.")
        pyautogui.failSafeCheck()
        foreground = user32.GetForegroundWindow()
        if foreground != self.handle:
            owned_menu = (getattr(self, "menu_open", False) and foreground
                          and user32.GetAncestor(foreground, 3) == user32.GetAncestor(self.handle, 3))
            if not owned_menu and getattr(self, "menu_open", False) and foreground and same_process(foreground, self.handle):
                # Some Qt popups omit Win32 ownership. Accept only a small popup
                # contained in the selected window, and only during Copy Text.
                popup, main = bounds(foreground), bounds(self.handle)
                owned_menu = (popup["width"] < main["width"] and popup["height"] < main["height"]
                              and popup["left"] >= main["left"] and popup["top"] >= main["top"]
                              and popup["left"] + popup["width"] <= main["left"] + main["width"]
                              and popup["top"] + popup["height"] <= main["top"] + main["height"])
            if not owned_menu:
                if self.config.get("debug_capture", False):
                    folder = ROOT / "diagnostics"
                    folder.mkdir(exist_ok=True)
                    detail = {"target": self.handle, "foreground": foreground,
                              "menu_open": getattr(self, "menu_open", False),
                              "same_process": bool(foreground and same_process(foreground, self.handle)),
                              "target_bounds": bounds(self.handle),
                              "foreground_bounds": bounds(foreground) if foreground else None}
                    (folder / "focus.json").write_text(json.dumps(detail), encoding="utf-8")
                raise ValueError("Target window lost focus. Action stopped.")

    def focus(self):
        if user32.GetForegroundWindow() != self.handle:
            user32.SetForegroundWindow(self.handle)
            time.sleep(0.15)
        self.check()

    def capture(self, calibrated=True):
        self.check()
        self.dpi = user32.GetDpiForWindow(self.handle) or 96
        self.scale = self.dpi / self.profile.get("reference_dpi", self.dpi)
        box = bounds(self.handle)
        actual = [box["width"], box["height"]]
        expected = [round(value*self.scale) for value in self.profile["size"]] if self.profile["size"] else None
        offset = content_offset(self.profile, actual, self.dpi)
        self.content_offset_x = offset or 0
        automatic = self.profile.get("auto_calibration", False)
        if calibrated and offset is None and not automatic:
            raise ValueError(f"Window size changed. Actual {actual}, calibrated {expected}, DPI {self.dpi}. Calibrate first.")
        with mss.mss() as screen:
            frame = np.asarray(screen.grab(box))[:, :, :3].copy()
        self.check()
        if bounds(self.handle) != box or (user32.GetDpiForWindow(self.handle) or 96) != self.dpi:
            raise ValueError("Window moved or display scaling changed during capture. Read the screen again.")
        if calibrated and automatic:
            geometry = (box["width"],box["height"],self.dpi)
            if getattr(self,"_auto_geometry",None) != geometry or self.profile.get("auto_state") != "chat":
                discovered = AutoCalibrator(self.profile).analyze(frame,self.dpi)
                self.check()
                if bounds(self.handle) != box:
                    raise ValueError("Window moved during automatic calibration. Try again.")
                self.profile = discovered
                self._auto_geometry = geometry
            self.scale, self.content_offset_x = 1, 0
        if self.config.get("debug_capture", False):
            # Opt-in local diagnostic frame, overwritten rather than accumulated.
            folder = ROOT / "diagnostics"
            folder.mkdir(exist_ok=True)
            name = "telegram" if self.profile.get("process_name", "").lower() == "telegram.exe" else "anonchat"
            cv2.imencode(".png", frame)[1].tofile(folder / (name + ".png"))
        return frame, box

    def observe(self):
        frame, _ = self.capture()
        if self.profile.get("auto_calibration") and self.profile.get("auto_state") != "chat":
            raise ValueError("No active chat detected. Open a conversation or use Search for partner.")
        regions = self.profile["regions"]
        if "chat_anchor" in self.profile["templates"]:
            try:
                self.find(frame, "chat_anchor")
            except ValueError as error:
                self._auto_geometry = None
                raise ValueError("No active message input detected. Chat may have ended or a dialog is open.") from error
        if "identity" not in regions:
            raise ValueError("Calibrate the identity region first.")
        identity = hashlib.sha256(crop(frame, self.region("identity")).tobytes()).hexdigest()
        if self.profile.get("read_mode") == "bubbles":
            if self.profile.get("text_source") == "clipboard":
                text = self.incoming_group(frame)
            else:
                text = self.incoming_group(frame)
        else:
            if "incoming" not in regions:
                raise ValueError("Calibrate the incoming-message region first.")
            text = self.ocr(crop(frame, self.region("incoming")))
        return Observation(identity, normalize(text))

    def incoming_group(self, frame):
        region = self.message_region(frame)
        pane = crop(frame, region)
        if not self.profile.get("incoming_color") or not self.profile.get("outgoing_color"):
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

    def ocr(self, image):
        return pytesseract.image_to_string(ocr_image(image), lang="eng", config="--psm 6", timeout=15)

    def read_bubble(self, frame, direction):
        regions = self.profile["regions"]
        if self.profile.get("auto_calibration") and not self.profile.get(direction + "_color"):
            pane = crop(frame,self.message_region(frame))
            self.profile.update(infer_colors(pane))
        color = self.profile.get(direction + "_color")
        if color is None and self.profile.get("auto_calibration"):
            return ""
        if "chat" not in regions or color is None:
            raise ValueError(f"Calibrate the chat pane and {direction} bubble sample first.")
        pane = crop(frame, self.message_region(frame))
        side = "left" if direction == "incoming" else "right"
        boxes = bubble_rectangles(pane, color, side, self.profile.get(direction + "_tolerance", 12))
        if not boxes:
            return ""
        text = self.ocr(crop(pane, boxes[-1]))
        if self.profile.get("timestamp_inside", False):
            return strip_timestamp(text)
        return normalize(text)

    def message_region(self, frame):
        region = self.region("chat")
        margin = self.profile.get("chat_bottom_from_anchor")
        if margin is not None:
            _, anchor_y = self.find(frame, "chat_anchor")
            region[3] = anchor_y - round(margin * self.scale) - region[1]
            if region[3] < 4:
                raise ValueError("Message pane is not available above the input row.")
        return region

    def copy_bubble(self, frame, direction, selected=None):
        """Use the normal application's Copy Text menu; never call a messaging API."""
        region = self.message_region(frame)
        pane = crop(frame, region)
        if self.profile.get("auto_calibration") and not self.profile.get(direction + "_color"):
            self.profile.update(infer_colors(pane))
        color = self.profile.get(direction + "_color")
        if color is None:
            if self.profile.get("auto_calibration"):
                return ""
            raise ValueError(f"Calibrate an {direction} bubble sample first.")
        side = "left" if direction == "incoming" else "right"
        boxes = bubble_rectangles(pane, color, side, self.profile.get(direction + "_tolerance", 12))
        if not boxes:
            return ""
        x, y, w, h = selected if selected is not None else boxes[-1]
        box = bounds(self.handle)
        self.check()
        before = user32.GetClipboardSequenceNumber()
        self.menu_open = True
        try:
            pyautogui.click(box["left"] + region[0] + x + min(w//2, 60),
                            box["top"] + region[1] + y + h//2, button="right")
            time.sleep(0.4)
            self.click("copy_text")
        finally:
            self.menu_open = False
        deadline = time.monotonic() + 2
        while user32.GetClipboardSequenceNumber() == before:
            self.check()
            if time.monotonic() >= deadline:
                raise ValueError("Copy Text did not update the clipboard; no message was read.")
            time.sleep(0.05)
        text = normalize(pyperclip.paste())
        fresh, _ = self.capture()
        # Compare the exact selected bubble and header, not animated media elsewhere.
        current_pane = crop(fresh, region)
        changed = np.mean(np.abs(crop(current_pane, (x,y,w,h)).astype(float) - crop(pane, (x,y,w,h)).astype(float)))
        identity = self.region("identity")
        if changed > 3 or not np.array_equal(crop(fresh, identity), crop(frame, identity)):
            raise ValueError("Chat content changed while copying; read it again.")
        if not text or len(text) > 8000:
            raise ValueError("Copied message is empty or too long.")
        return text

    def screen_state(self):
        try:
            frame, _ = self.capture()
        except CalibrationError:
            return "unknown"
        for name in ("blocked", "searching", "ended", "search", "chat_anchor", "empty_textbox"):
            if name not in self.profile["templates"]:
                continue
            try:
                self.find(frame, name)
                return {"search": "home", "chat_anchor": "chat", "empty_textbox": "chat"}.get(name, name)
            except ValueError:
                continue
        return "unknown"

    def wait_for_chat(self, seconds=30):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.check()
            state = self.screen_state()
            if state == "chat":
                return True
            if state == "blocked":
                raise ValueError("Account or sign-in screen detected. Operator action required.")
            if self.cancelled.wait(0.5):
                self.check()
        return False

    def template(self, name):
        path = self.profile["templates"].get(name)
        if not path:
            raise ValueError(f"Calibrate the {name} reference first.")
        image = cv2.imdecode(np.fromfile(ROOT / path, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
        image_dpi = self.profile.get("template_dpi", {}).get(name, self.profile.get("reference_dpi", self.dpi))
        scale = self.dpi / image_dpi
        if image is not None and scale != 1:
            image = cv2.resize(image, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        return image

    def click(self, name):
        frame, box = self.capture()
        x, y = self.find(frame, name)
        self.check()
        if bounds(self.handle) != box:
            raise ValueError("Window moved during matching; action stopped.")
        pyautogui.click(box["left"] + x, box["top"] + y)
        time.sleep(0.3)

    def send(self, expected, reply):
        if self.observe() != expected:
            raise ValueError("Screen changed; draft blocked.")
        # The reference must show the entire EMPTY input with its placeholder.
        self.click("empty_textbox")
        for character in reply:
            self.check()
            if " " <= character <= "~":
                pyautogui.write(character, interval=0.05)
            else:
                keyboard.write(character, exact=True)
                time.sleep(0.05)
        if self.observe() != expected:
            raise ValueError("Screen changed during typing. Inspect the unsent draft.")
        return self.submit_and_verify(expected, reply)

    def finish_pending(self, expected, reply):
        """Explicit recovery: submit an exact visible draft without typing again."""
        if self.observe() != expected:
            raise ValueError("Conversation or incoming message changed; pending submission blocked.")
        settings = self.profile.get("draft_from_anchor")
        if not settings:
            raise ValueError("Visible-draft recovery is not calibrated for this platform.")
        frame, _ = self.capture()
        _, anchor_y = self.find(frame, "chat_anchor")
        region = [getattr(self, "content_offset_x", 0) + round(settings["x"] * self.scale),
                  anchor_y + round(settings["top"] * self.scale),
                  round(settings["width"] * self.scale), round(settings["height"] * self.scale)]
        if normalize(self.ocr(crop(frame, region))) != normalize(reply):
            raise ValueError("Visible draft does not exactly match the pending reply. Recovery stopped.")
        if self.observe() != expected:
            raise ValueError("Screen changed while checking the draft. Recovery stopped.")
        return self.submit_and_verify(expected, reply)

    def submit_and_verify(self, expected, reply):
        if self.profile.get("send_method", "button") == "enter":
            self.check()
            pyautogui.press("enter")
        else:
            self.click("send")
        # Observe the outgoing bubble. This verifies UI submission, not server delivery.
        if self.profile.get("outgoing_color") is not None or self.profile.get("auto_calibration"):
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                if self.cancelled.wait(0.5):
                    self.check()
                frame, _ = self.capture()
                identity = hashlib.sha256(crop(frame, self.region("identity")).tobytes()).hexdigest()
                if identity != expected.identity:
                    raise ValueError("Conversation changed while checking the outgoing message.")
                outgoing = (self.copy_bubble(frame, "outgoing") if self.profile.get("text_source") == "clipboard"
                            else normalize(self.read_bubble(frame, "outgoing")))
                if outgoing == reply:
                    return True
        return False

    def search(self, action):
        if action not in {"search", "next"}:
            raise ValueError("Unsupported matching action.")
        self.click(action)
