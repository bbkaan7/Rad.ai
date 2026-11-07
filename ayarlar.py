"""Local ADB and Ollama settings; no platform API credentials."""

from dataclasses import dataclass, field
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parent
VERSION = "0.1.15"


@dataclass(frozen=True)
class Settings:
    ollama_url: str = "http://localhost:11434/api/generate"
    model: str = "llama3.2:1b"
    context_messages: int = 5
    debounce_seconds: float = 3.0
    llm_timeout_seconds: float = 300.0
    typing_enabled: bool = True
    typing_delay_seconds: float = 5.0
    typing_interval_seconds: float = 1.5
    adb_host: str = "127.0.0.1"
    adb_port: int = 5037
    adb_serial: str = ""
    adb_device_host: str = "127.0.0.1"
    adb_device_port: int = 5555
    adb_poll_seconds: float = 1.0
    accessibility_enabled: bool = False
    accessibility_port: int = 18765
    concurrent_monitoring: bool = False
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
    return validate(Settings(**values))


def validate(settings):
    import math
    from urllib.parse import urlparse
    if not settings.model.strip() or len(settings.model)>120:
        raise ValueError('Enter a model name of 1-120 characters.')
    url=urlparse(settings.ollama_url)
    if url.scheme not in ('http','https') or not url.hostname or url.username or url.password:
        raise ValueError('Enter a valid Ollama HTTP URL without credentials.')
    for name in ('debounce_seconds','llm_timeout_seconds','typing_delay_seconds','typing_interval_seconds'):
        if not math.isfinite(float(getattr(settings,name))):raise ValueError(name+' must be finite.')
    if not 10<=settings.llm_timeout_seconds<=1800:
        raise ValueError('LLM timeout must be 10-1800 seconds.')
    if not 0<=settings.debounce_seconds<=10 or not 1<=settings.typing_delay_seconds<=60 or not .5<=settings.typing_interval_seconds<=10:
        raise ValueError('Invalid reply timing: debounce 0-10, typing delay 1-60, interval 0.5-10 seconds.')
    if settings.context_messages != 5:
        raise ValueError("context_messages must be 5 for this release.")
    if settings.adb_poll_seconds < 0.25 or settings.debounce_seconds < 0:
        raise ValueError("Invalid polling or debounce interval.")
    if settings.adb_switch_seconds < 0:
        raise ValueError("Invalid Android switch delay.")
    if settings.adb_focus_seconds < 5 or settings.adb_launch_cooldown_seconds < 1 or settings.adb_error_backoff_seconds < 1:
        raise ValueError("Android timing values are too short for stable app switching.")
    if not 1024 <= settings.accessibility_port <= 65535:
        raise ValueError("Invalid local accessibility port.")
    return settings


def save(settings,path=None):
    from dataclasses import asdict
    import os
    import tempfile
    validate(settings)
    path=Path(path) if path else ROOT/'settings.json'
    fd,temporary=tempfile.mkstemp(prefix='rad-settings-',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf-8') as stream:
            json.dump(asdict(settings),stream,indent=2,ensure_ascii=False)
            stream.write('\n');stream.flush();os.fsync(stream.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)
