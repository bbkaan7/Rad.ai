"""Start the supervised v0.2.0 development build."""

import argparse
import ctypes
import os
import traceback
from pathlib import Path

from assistant import VERSION


def main():
    parser = argparse.ArgumentParser(description="Desktop Assistant")
    parser.add_argument("--version", action="version", version=VERSION)
    parser.parse_args()
    if os.name != "nt":
        parser.error("This desktop adapter requires Windows.")
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()
    from assistant.ui import run
    run()


if __name__ == "__main__":
    try:
        main()
    except Exception:
        detail = traceback.format_exc()
        path = Path(__file__).resolve().parent / "startup-error.log"
        path.write_text(detail, encoding="utf-8")
        if os.name == "nt":
            ctypes.windll.user32.MessageBoxW(None, "Unable to start. See startup-error.log in the application folder.", "Desktop Assistant", 0x10)
        raise
