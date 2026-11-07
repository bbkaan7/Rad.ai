"""Desktop chat MVP: one cycle per hotkey, Windows / primary monitor."""

import argparse
import ctypes
import logging
import os
import re
import threading
import time

# Align screenshot pixels and mouse coordinates under Windows scaling.
# Configure DPI awareness before importing screen and mouse libraries.
if os.name == "nt":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()

import cv2
import keyboard
import mss
import numpy as np
import pyautogui
import pytesseract
import requests

import settings as a

VERSION = "0.5.0"

log = logging.getLogger(__name__)
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1
if a.TESSERACT_PATH:
    pytesseract.pytesseract.tesseract_cmd = a.TESSERACT_PATH

trigger_event = threading.Event()
stop_event = threading.Event()
busy_lock = threading.Lock()


def capture_screen(region=None):
    """Return a BGR screenshot and its left/top screen offset."""
    # Create the MSS instance in the thread that captures the screen.
    with mss.mss() as screen:
        area = dict(screen.monitors[1] if region is None else region)
        if area["width"] <= 0 or area["height"] <= 0:
            raise ValueError("Screen region dimensions must be positive.")
        image = np.array(screen.grab(area))
    return cv2.cvtColor(image, cv2.COLOR_BGRA2BGR), (area["left"], area["top"])


def clean_message(text):
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x0c", "").strip()
    if a.MESSAGE_SELECTION == "last_paragraph":
        text = re.split(r"\n\s*\n", text)[-1]
    elif a.MESSAGE_SELECTION != "region":
        raise ValueError("MESSAGE_SELECTION must be 'region' or 'last_paragraph'.")
    return " ".join(text.split())


def read_text(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Invert light text on a dark background for OCR.
    if np.mean(binary) < 127:
        binary = cv2.bitwise_not(binary)
    text = pytesseract.image_to_string(
        binary, lang=a.OCR_LANGUAGE, config=a.OCR_CONFIG, timeout=a.OCR_TIMEOUT
    )
    return clean_message(text)


def generate_reply(message):
    response = requests.post(
        a.OLLAMA_URL,
        json={"model": a.MODEL, "prompt": a.PROMPT.format(message=message), "stream": False},
        timeout=a.API_TIMEOUT,
    )
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("The API response must be a JSON object.")
    if data.get("error"):
        raise ValueError(f"Ollama error: {data['error']}")
    reply = data.get("response")
    if not isinstance(reply, str) or not reply.strip():
        raise ValueError("The LLM returned an empty or invalid reply.")
    # Newlines can accidentally send messages in some applications.
    reply = " ".join(reply.split())
    if len(reply) > a.MAX_REPLY_LENGTH:
        raise ValueError("The LLM reply exceeds the maximum length.")
    return reply


def find_element(reference):
    """Return the best match above the threshold, or None."""
    if not reference.is_file():
        log.error("Element not found: missing reference image (%s).", reference.name)
        return None
    # imdecode + fromfile supports Unicode file paths on Windows.
    template = cv2.imdecode(np.fromfile(reference, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if template is None or float(template.std()) < 1:
        log.error("Element not found: unreadable or featureless reference image.")
        return None
    image, (left, top) = capture_screen(a.SEARCH_REGION)
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    h, w = template.shape
    if h > gray.shape[0] or w > gray.shape[1]:
        log.error("Element not found: reference image exceeds the search region.")
        return None
    result = cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED)
    _, confidence, _, location = cv2.minMaxLoc(result)
    if not np.isfinite(confidence) or confidence < a.MATCH_THRESHOLD:
        log.error("Element not found: %s (confidence=%.3f).", reference.name, confidence)
        return None
    return left + location[0] + w // 2, top + location[1] + h // 2


def check_cancelled():
    if stop_event.is_set():
        raise InterruptedError("Stopped by the user.")
    pyautogui.failSafeCheck()


def find_and_click(reference):
    check_cancelled()
    center = find_element(reference)
    if center is None:
        return False
    check_cancelled()
    pyautogui.click(*center)
    time.sleep(a.UI_DELAY)
    return True


def type_reply(reply):
    # Check cancellation between characters and preserve Unicode characters.
    for character in reply:
        check_cancelled()
        if " " <= character <= "~":
            pyautogui.write(character, interval=a.TYPING_INTERVAL)
        else:
            keyboard.write(character, exact=True)
            time.sleep(a.TYPING_INTERVAL)


def run_cycle():
    check_cancelled()
    log.info("Cycle started; capturing the screen.")
    image, _ = capture_screen(a.CHAT_REGION)
    log.info("Screen captured; running OCR.")
    message = read_text(image)
    if not message:
        log.warning("No readable message; cycle cancelled.")
        return
    log.info("Message read; waiting for the LLM reply.")
    reply = generate_reply(message)
    check_cancelled()
    if not find_and_click(a.TEXTBOX_IMAGE):
        return
    # Assume an empty textbox; do not erase existing drafts.
    type_reply(reply)
    time.sleep(a.UI_DELAY)
    check_cancelled()
    if a.SEND_METHOD == "enter":
        pyautogui.press("enter")
    elif not find_and_click(a.SEND_IMAGE):
        log.warning("Reply remains in the textbox; not sent. Check the textbox before pressing F9 again.")
        return
    log.info("Send action completed (delivery is not verified).")


def trigger_cycle():
    # Ignore hotkeys while busy; allow only one cycle at a time.
    if stop_event.is_set():
        return
    if not busy_lock.acquire(blocking=False):
        log.info("Hotkey detected; the previous cycle is still running.")
        return
    log.info("Hotkey detected; starting a cycle.")
    trigger_event.set()


def key_test():
    """Test trigger keys only; do not read the screen or send messages."""
    if os.name == "nt":
        log.info("WINDOWS KEY TEST: try F9 / Ctrl+Alt+9. Exit: F10 or Ctrl+C. No messages will be sent.")
        try:
            windows_key_listener(test=True)
        except KeyboardInterrupt:
            stop_event.set()
        return

    def log_event(event):
        # Do not log ordinary typing.
        if event.name in {"f9", "f10", "9"}:
            log.info("Key detected: %s | %s", event.name, event.event_type)

    hook = keyboard.hook(log_event)
    try:
        log.info("KEY TEST: try F9, Fn+F9 or 9. Exit: Ctrl+C. No messages will be sent.")
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        keyboard.unhook(hook)


def windows_key_reader():
    """Read only five key states without installing a keyboard hook."""
    read_keys = ctypes.windll.user32.GetAsyncKeyState
    read_keys.argtypes = [ctypes.c_int]
    read_keys.restype = ctypes.c_short
    key_codes = {"f9": 0x78, "f10": 0x79, "ctrl": 0x11, "alt": 0x12, "9": 0x39}

    def pressed_keys():
        # Use only the currently-pressed high bit; the low bit is unreliable.
        return {name for name, code in key_codes.items() if read_keys(code) & 0x8000}

    return pressed_keys


def windows_key_listener(test=False):
    """Poll every 20 ms; trigger once per press/release sequence."""
    try:
        read_keys = windows_key_reader()
        previous = set()
        pending = False
        while not stop_event.wait(0.02):
            current = read_keys()
            if test:
                for key in sorted(current - previous):
                    log.info("Key detected (Windows): %s | down", key)
                for key in sorted(previous - current):
                    log.info("Key detected (Windows): %s | up", key)
            if "f10" in current:
                log.info("F10 detected; stopping.")
                stop_event.set()
                return
            active = "f9" in current or {"ctrl", "alt", "9"}.issubset(current)
            previously_active = "f9" in previous or {"ctrl", "alt", "9"}.issubset(previous)
            if active and not previously_active:
                # Discard presses that started while a cycle was running.
                pending = test or not busy_lock.locked()
                if not test:
                    log.info("Hotkey pressed (Windows). Release all hotkey keys.")
            if pending and not current.intersection({"f9", "ctrl", "alt", "9"}):
                pending = False
                if test:
                    log.info("Trigger successful (test); no chat action performed.")
                else:
                    trigger_cycle()
            previous = current
    except Exception:
        log.exception("The Windows key listener failed.")
        stop_event.set()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    parser = argparse.ArgumentParser(description="Desktop Chat Alpha")
    parser.add_argument("--version", action="version", version=f"Desktop Chat Alpha {VERSION}")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--key-test", action="store_true", help="Test key detection without sending messages")
    mode.add_argument("--once", action="store_true", help="Run one cycle and send after a 3-second delay, without a hotkey")
    args = parser.parse_args()
    if args.key_test:
        key_test()
        return
    if a.SEND_METHOD not in {"button", "enter"} or not 0 < a.MATCH_THRESHOLD <= 1:
        raise ValueError("Invalid send method or match threshold.")
    hotkeys = []
    listener = None
    try:
        if args.once:
            log.info("A cycle will run and send a reply in 3 seconds; open the target chat. Cancel: Ctrl+C.")
            time.sleep(3)
            try:
                run_cycle()
            except (pyautogui.FailSafeException, InterruptedError):
                log.warning("Single cycle stopped.")
            except Exception:
                log.exception("Single cycle failed; check the textbox.")
            return
        if os.name == "nt":
            listener = threading.Thread(target=windows_key_listener, daemon=True)
            listener.start()
            log.info("Key input: Windows polling; no keyboard hook installed.")
        else:
            # Use a separate callback for each registration to avoid cleanup collisions.
            hotkeys.append(keyboard.add_hotkey("f9", lambda: trigger_cycle(), trigger_on_release=True))
            hotkeys.append(keyboard.add_hotkey("ctrl+alt+9", lambda: trigger_cycle(), trigger_on_release=True))
            hotkeys.append(keyboard.add_hotkey("f10", stop_event.set, trigger_on_release=True))
        log.info("Ready (v%s). Press and release F9 or Ctrl+Alt+9: one cycle | F10 or Ctrl+C: exit.", VERSION)
        while not stop_event.is_set():
            if not trigger_event.wait(timeout=0.1):
                continue
            trigger_event.clear()
            try:
                run_cycle()
            except (pyautogui.FailSafeException, InterruptedError):
                log.warning("Automation stopped; partial text may remain in the textbox.")
                stop_event.set()
            except Exception:
                # Keep the listener alive after OCR, API, image or operating-system errors.
                log.exception("Cycle failed. Check the textbox before starting another cycle.")
            finally:
                busy_lock.release()
    except KeyboardInterrupt:
        stop_event.set()
    finally:
        stop_event.set()
        if listener is not None:
            listener.join(timeout=1)
        for hotkey in hotkeys:
            keyboard.remove_hotkey(hotkey)


if __name__ == "__main__":
    main()
