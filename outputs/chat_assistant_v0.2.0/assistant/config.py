"""Local configuration; no credentials are stored here."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "profiles.json"


def defaults():
    return {
        "model": "llama3.2:1b",
        "ollama_url": "http://localhost:11434/api/chat",
        "tesseract": r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        "profiles": {
            name: {"window_title": title, "process_name": process,
                   "regions": {}, "templates": {}, "size": None}
            for name, title, process in [("anonchat", "BlueStacks App Player 3", "HD-Player.exe"),
                                         ("telegram", "", "Telegram.exe")]
        },
    }


def load():
    if not CONFIG.exists():
        return defaults()
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def save(config):
    temporary = CONFIG.with_suffix(".tmp")
    temporary.write_text(json.dumps(config, indent=2), encoding="utf-8")
    temporary.replace(CONFIG)
