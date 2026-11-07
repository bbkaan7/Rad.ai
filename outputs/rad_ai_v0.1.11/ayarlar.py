"""Local ADB and Ollama settings; no platform API credentials."""

from dataclasses import dataclass, field
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
VERSION = "0.1.11"


@dataclass(frozen=True)
class Settings:
    ollama_url: str = "http://localhost:11434/api/generate"
    model: str = "llama3.2:1b"
    context_messages: int = 5
    debounce_seconds: float = 3.0
    adb_host: str = "127.0.0.1"
    adb_port: int = 5037
    adb_serial: str = ""
    adb_device_host: str = "127.0.0.1"
    adb_device_port: int = 5555
    adb_poll_seconds: float = 1.0
    selectors: dict = field(default_factory=dict)
    anon_greeting: bool = True
    telegram_selectors: dict = field(default_factory=dict)
    adb_switch_seconds: float = 0.35
    adb_activities: dict = field(default_factory=dict)
    adb_focus_seconds: float = 12.0
    adb_launch_cooldown_seconds: float = 8.0
    adb_error_backoff_seconds: float = 5.0


def load():
    path = ROOT / "settings.json"
    values = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    allowed = set(Settings.__dataclass_fields__)
    unknown = set(values) - allowed
    if unknown:
        raise ValueError("Unknown settings: " + ", ".join(sorted(unknown)))
    settings = Settings(**values)
    if settings.context_messages != 5:
        raise ValueError("context_messages must be 5 for this release.")
    if settings.adb_poll_seconds < 0.25 or settings.debounce_seconds < 0:
        raise ValueError("Invalid polling or debounce interval.")
    if settings.adb_switch_seconds < 0:
        raise ValueError("Invalid Android switch delay.")
    if settings.adb_focus_seconds < 5 or settings.adb_launch_cooldown_seconds < 1 or settings.adb_error_backoff_seconds < 1:
        raise ValueError("Android timing values are too short for stable app switching.")
    return settings
