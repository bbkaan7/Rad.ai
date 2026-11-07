"""Local-only GUI checks; no platform connection or messages are sent."""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from rad.gui import Panel
from ayarlar import VERSION


def event(key, title, category="New partner", messages=None):
    return {"type": "chat", "key": key, "title": title, "category": category,
            "paused": False, "uncertain": False, "closed": False,
            "messages": messages or [{"id": 1, "role": "user", "text": "Hello"}]}


p = Panel()
from unittest.mock import AsyncMock
p.worker.engine.open_friend = AsyncMock()
try:
    p.deiconify()
    p.update()
    assert VERSION == "0.1.15"
    p.tabs.set('Settings');p.platform_selected();p.update()
    assert p.settings_panel.winfo_ismapped() and not p.chat_panel.winfo_ismapped()
    assert p.setting_fields['model'].get()==p.worker.settings.model
    timeout=p.setting_fields['llm_timeout_seconds']
    original=timeout.get();timeout.delete(0,'end');timeout.insert(0,'nan')
    p.save_settings();assert 'Settings not saved' in p.status.cget('text')
    timeout.delete(0,'end');timeout.insert(0,original)
    p.tabs.set('AnonChat');p.platform_selected();p.update()
    assert not p.settings_panel.winfo_ismapped() and p.chat_panel.winfo_ismapped()
    assert len(p.brand_images) == 1
    assert ("Telegram", "Chats") in p.sections
    assert ("AnonChat", "New partner") in p.sections
    assert ("AnonChat", "Friends") in p.sections
    assert ("AnonChat", "Past matches") not in p.sections
    assert hasattr(p, "window_icon")
    for mode in ("Light", "Dark", "Light"):
        p.set_theme(mode)
        p.feed.canvas.configure(width=750, height=400)
        p.update()
        p.feed.draw()
        assert bool(p.feed.canvas.find_withtag("paw")) == (mode == "Light")
        p.feed.set_messages([{"role": "user", "text": "This is a local display test."},
                             {"role": "assistant", "text": "A second message in a separate bubble."}])
        p.update()
        assert len(p.feed.canvas.find_withtag("message")) == 4
        assert p.feed.canvas.cget("background") == ("#FFFCFB" if mode == "Light" else "#201C27")
    p.set_theme("Dark")
    assert p.theme_toggle.cget("text") == "☾"
    p.toggle_theme()
    assert p.theme_toggle.cget("text") == "☀" and p.theme_mode == "Light"

    # Reclassifying the same identity must move one button and retain the transcript.
    temporary = event("anonchat:local-test", "AnonChat · New partner")
    p.handle_event(temporary)
    p.select(temporary["key"])
    assert p.buttons[temporary["key"]].master is p.sections[("AnonChat", "New partner")]
    old_button = p.buttons[temporary["key"]]
    friend = dict(temporary, title="AnonChat · Test Friend", category="Friends")
    p.handle_event(friend)
    assert len(p.buttons) == 1
    assert not old_button.winfo_exists()
    assert p.buttons[temporary["key"]].master is p.sections[("AnonChat", "Friends")]
    assert p.feed.messages == temporary["messages"]

    # Background updates stay in their tab and never select another platform.
    telegram = event("telegram:local-test", "Telegram Test", category="Chats")
    p.handle_event(telegram)
    assert p.selected == temporary["key"] and p.tabs.get() == "AnonChat"
    p.entry.insert("1.0", "Draft for this friend")
    p.select(telegram["key"])
    assert not p.entry.get("1.0", "end").strip()
    p.entry.insert("1.0", "Separate Telegram draft")
    p.select(temporary["key"])
    assert p.entry.get("1.0", "end").strip() == "Draft for this friend"
    p.select(telegram["key"])
    assert p.entry.get("1.0", "end").strip() == "Separate Telegram draft"

    # A closed nonfriend removes UI state, pending draft and message selection.
    closed = event("anonchat:closed-test", "AnonChat · New partner")
    p.handle_event(closed)
    p.select(closed["key"])
    p.entry.insert("1.0", "Must not reach a future stranger")
    p.reply_to = 1
    p.save_draft()
    p.handle_event({"type": "chat_removed", "key": closed["key"]})
    assert closed["key"] not in p.chats and closed["key"] not in p.buttons
    assert closed["key"] not in p.drafts
    assert p.selected is None and p.reply_to is None
    assert p.heading.cget("text") == "Chat closed"
    assert p.feed.messages == [] and p.message_options == {}
    assert p.message_picker.get() == "Select a message"
    assert not p.entry.get("1.0", "end").strip()
    p.handle_event(telegram)
    assert p.selected is None and p.heading.cget("text") == "Chat closed"
    p.handle_event({"type": "chat_removed", "key": closed["key"]})
    assert p.chats[temporary["key"]]["category"] == "Friends"

    p.handle_event({'type':'notification','id':'test','package':'io.anonchat','title':'Local Test','text':'Preview only'})
    assert len(p.notification_buttons)==1
    assert 'awaiting verification' in p.notification_buttons['test'].cget('text')
    p.handle_event({'type':'notification_verified','id':'test','key':temporary['key']})
    assert not p.notification_buttons

    # Programmatic auto changes must update the actual switch value as well as its label.
    p.handle_event({"type": "auto", "value": True})
    assert p.auto.get() == 1 and p.auto.cget("text") == "Auto-reply: ON"
    p.handle_event({"type": "auto", "value": False})
    assert p.auto.get() == 0 and p.auto.cget("text") == "Auto-reply: OFF"

    calls = []
    async def fake_start():
        calls.append("start")
        await asyncio.sleep(.1)
    p.worker.engine.start_anon = fake_start
    p.start_anon()
    p.start_anon()
    assert p.start_pending and p.start_anon_button.cget("state") == "disabled"
    deadline = time.monotonic() + 3
    while p.start_pending and time.monotonic() < deadline:
        p.update()
        time.sleep(.02)
    assert calls == ["start"]
    assert not p.start_pending and p.start_anon_button.cget("state") == "normal"

    p.worker.submit(p.worker.engine.select_platform("telegram")).result(5)
    assert p.worker.engine.android.selected_package is None
    print("Theme, icons, start button, auto switch, chat removal, friend relocation and draft isolation passed.")
    for filename in ("rad-logo.png", "rad-paw.png"):
        with Image.open(Path("assets") / filename) as image:
            assert image.mode == "RGBA" and image.getchannel("A").getextrema() == (0, 255)
    with Image.open("assets/rad-paw.ico") as icon:
        assert (16, 16) in icon.ico.sizes() and (256, 256) in icon.ico.sizes()
    print("Transparent assets and Windows ICO validated.")
finally:
    p.closing = True
    p.worker.submit(p.worker.engine.close()).result(15)
    p.worker.loop.call_soon_threadsafe(p.worker.loop.stop)
    p.worker.thread.join(5)
    p.destroy()
