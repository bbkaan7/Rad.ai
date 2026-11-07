# Rad.ai v0.2.6 — API/ADB architecture

The active project is now `main.py`, `ayarlar.py`, `settings.json`, `requirements.txt`
and the `rad/` package in this directory. Legacy screen/OCR releases are historical
backups, not imports or dependencies of this application. The runtime does not use
mss, pytesseract, OpenCV, PyAutoGUI, keyboard hooks, desktop screenshots or mouse input.

## Start

Open **Rad.ai.exe**, or **Start.cmd** for startup diagnostics. The project has an
isolated `.venv` with the requested dependencies installed. On another machine:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

All controls are English. The dark CustomTkinter panel lists chats on the left and
live incoming/outgoing text on the right. Select a chat, type and press **Send
manually** to take over that chat. **Resume selected** restores eligibility for
future automatic replies. Global **Auto-reply** starts OFF. While OFF, incoming
events still update the panel. Turning it off suppresses late model results but
cannot undo an already submitted network/device send.

The UI stays on the Tk thread. A dedicated asyncio loop runs networking, generation,
presence and polling. Blocking ppadb calls run through asyncio.to_thread with shell
socket timeouts. No account connection or outgoing message is initiated on launch.

After GUI authentication and XML setup, optional service mode is available:
`python main.py --headless --auto-reply`. It uses the same engine without Tk.
Omit `--auto-reply` for receive-only mode. Stop with Ctrl+C. Do not run GUI and
service instances simultaneously against the same session/device.

## Telegram QR login (default)

Restart Rad.ai and click **Connect Telegram (QR)**. On the already signed-in phone,
open Telegram > Settings > Devices > Link Desktop Device and scan the code in
Rad.ai. No SMS access is required for this method. Two-step verification, if enabled,
still requires your password. QR codes refresh automatically and are never saved or
logged. Close the QR window to cancel. Approval must be done by the account owner.
If there is no signed-in mobile session and no access to the phone number, this
software cannot bypass account authentication. The previous code flow remains
available with `telegram_login_method: "code"` in settings.json.

## Telegram normal user account

Obtain your own application API ID and API hash from https://my.telegram.org.
Credentials may be stored locally in ignored `runtime/credentials.json` using
`api_id`, `api_hash` and optional `phone` fields. Environment variables
`TELEGRAM_API_ID`, `TELEGRAM_API_HASH` and `TELEGRAM_PHONE` override local values.
The local credential file is excluded from release archives. Restart Rad.ai after
changing credentials. Click **Connect Telegram**, then enter your phone, login code and
two-step password in Rad.ai's local sign-in dialogs as requested.

Telethon uses MTProto with a normal phone-number account. There is no BotFather,
bot token, Bot API or Telegram Business integration. The session is stored under
`runtime/telegram.session`; keep it private and exclude it from shared archives.
The adapter imports the last five text messages from up to 100 private user dialogs
as context without auto-replying to old history. New private text messages arrive
through an event listener. Groups, bots, Saved Messages and media-only events are
excluded in this release.

While connected, the adapter requests online presence approximately every 50 seconds.
This is best effort; Telegram controls visibility and privacy rules still apply.
During model generation Telethon's async `client.action(peer, "typing")` maintains
the typing indicator. API rate limits are not bypassed. Send failures pause that chat;
an uncertain outcome is never retried automatically.

## BlueStacks / AnonChat ADB

The current local setup uses `127.0.0.1:5585` and package `io.anonchat`. Selectors
are now configured from a live UI XML dump. React Native exposes no stable IDs for
most chat controls, so `rad-role` selectors use structural XML rules implemented
in `rad/anon_xml.py`: header above the message list, message text with sibling
timestamps and left/right alignment, labelled bio, input row and its Send control.
These rules are based on the observed app layout, not hard-coded pixel coordinates.
Incoming text and bio extraction were verified; actual outgoing sending has not
been performed for this configuration. Future layout changes can require updates.

Install Android platform-tools, start its ADB server, enable BlueStacks ADB yourself,
and keep AnonChat open inside the emulator. Windows focus, visible pixels and the
Windows mouse are not used. BlueStacks must still run: ADB is not a replacement for
the Android application and does not make AnonChat an API service.

Set the actual device endpoint and, when necessary, serial in `settings.json`.
The ADB server port (usually 5037) and emulator device port are different. 5555 is
only a configurable starting value; it is not a verified BlueStacks port here.

Configure `selectors.package`, `identity`, `incoming` and `outgoing` using an actual
UI Automator XML dump from the installed app. Selectors are exact XML attributes,
for example `{"resource-id":"your.actual.package:id/message_text"}`. That example
is illustrative, not a known AnonChat ID. Incoming/outgoing selectors must select
distinct text nodes; identity must identify the current match. Input, Send,
Search/Next and optional bio selectors should also be checked against that XML.

Missing selectors stop connection clearly rather than guessing at messages or
coordinates. Some apps do not expose their content in accessibility XML; if AnonChat
does not, this adapter cannot read those messages without a different supported
interface. OCR fallbacks are intentionally absent.

The adapter obtains `uiautomator dump` XML, parses text and bounds, and uses `input
tap` and `input text`. Before sending it validates the selected match, empty input,
exact typed text and an outgoing text occurrence. Invalid or ambiguous states stop
input. Android `input text` supports printable ASCII here; emoji/non-ASCII and a
literal `%s` are rejected before typing. Telegram supports Unicode normally.

The XML polling baseline does not auto-reply to old history. New ordered occurrences
are found by overlapping successive lists. A lost overlap pauses the adapter rather
than guessing. If identical messages fully replace an identical visible viewport,
XML without stable message IDs cannot distinguish that event. One AnonChat match
is active per emulator adapter; Telegram can handle independent private chats.

When auto-reply is enabled, a newly observed AnonChat matching transition can send
the fixed `hii :3` without an LLM call, followed by a bio-based opener. The global
OFF toggle also disables greetings in this architecture. Existing chats on initial
connection do not receive a new greeting. No media, camera or video functions exist.

## Ollama and context

The adapter uses aiohttp POST requests to
`http://localhost:11434/api/generate`, model `llama3.2:1b`, with streaming disabled.
Each prompt contains the last five messages total (incoming and outgoing combined),
isolated per chat. Requests have timeouts and at most two concurrent model calls.
Successive incoming messages are debounced. If new text arrives during generation,
the stale draft is discarded and generation repeats with the refreshed context.
Messages arriving while a send is in progress remain eligible for the next reply.

This architecture uses one model generation per reply, matching the requested
/api/generate context flow. Conversation memory is temporary; Telegram's login
session is persisted, but customer histories are not written to disk.

## Verification

Run `.venv\Scripts\python.exe -m unittest discover -s tests -v`.
Tests use synthetic messages/XML and mocked adapters, without contacting accounts.
Live Telegram login and BlueStacks selectors have not been configured or validated.
Do not interpret a passing unit suite as a guarantee of error-free external apps.

Primary references:
- https://docs.telethon.dev/en/stable/modules/client.html
- https://github.com/Swind/pure-python-adb
- https://docs.ollama.com/api/generate
- https://customtkinter.tomschimansky.com/documentation/
