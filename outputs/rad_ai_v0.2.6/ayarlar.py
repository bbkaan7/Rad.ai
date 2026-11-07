"""Local settings. Credentials live in ignored runtime storage or the environment."""

from dataclasses import dataclass, field
from pathlib import Path
import json
import os

ROOT = Path(__file__).resolve().parent
VERSION = "0.2.6"


@dataclass(frozen=True)
class Settings:
    api_id: int = 0
    api_hash: str = field(default="", repr=False)
    phone: str = field(default="", repr=False)
    telegram_login_method: str = "qr"
    session: Path = ROOT / "runtime" / "telegram"
    ollama_url: str = "http://localhost:11434/api/generate"
    model: str = "llama3.2:1b"
    context_messages: int = 5
    debounce_seconds: float = 0.8
    adb_host: str = "127.0.0.1"
    adb_port: int = 5037
    adb_serial: str = ""
    adb_device_host: str = "127.0.0.1"
    adb_device_port: int = 5555
    adb_poll_seconds: float = 1.0
    selectors: dict = field(default_factory=dict)
    anon_greeting: bool = True


def load():
    path = ROOT / "settings.json"
    values = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    allowed = set(Settings.__dataclass_fields__) - {"api_id", "api_hash", "phone", "session"}
    unknown = set(values) - allowed
    if unknown:
        raise ValueError("Unknown settings: " + ", ".join(sorted(unknown)))
    credentials_path = ROOT / "runtime" / "credentials.json"
    credentials = json.loads(credentials_path.read_text(encoding="utf-8")) if credentials_path.exists() else {}
    settings = Settings(**values,
                        api_id=int(os.getenv("TELEGRAM_API_ID", str(credentials.get("api_id", 0)))),
                        api_hash=os.getenv("TELEGRAM_API_HASH", credentials.get("api_hash", "")),
                        phone=os.getenv("TELEGRAM_PHONE", credentials.get("phone", "")))
    if settings.context_messages != 5:
        raise ValueError("context_messages must be 5 for this release.")
    if settings.telegram_login_method not in {"qr", "code"}:
        raise ValueError("telegram_login_method must be qr or code.")
    if settings.adb_poll_seconds < 0.25 or settings.debounce_seconds < 0:
        raise ValueError("Invalid polling or debounce interval.")
    return settings
