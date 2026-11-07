# Rad.ai v0.2.9 — shared Android ADB architecture

## Start

Open **Rad.ai.exe** or **Start.cmd**. Close older Rad.ai instances first: only one
controller should operate this emulator. The existing two-tab CustomTkinter panel,
manual composer, Auto-reply switch, Start cycle, themes and chat history remain.

On a new machine:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Enable BlueStacks Android debugging and start its ADB server. The configured device
is `127.0.0.1:5585`, connected through the local ADB server on port `5037`.
Install and sign into both Android apps manually:

- AnonChat: `io.anonchat`
- Vidogram: `org.vidogram.messenger`, English UI

Click **Connect AnonChat** and **Connect Telegram (ADB)**. No platform API credentials,
phone-number entry, login-code dialog or QR sign-in is present in Rad.ai. Existing
Android sessions are used. Old desktop network session files are not read.
The app does not connect or send anything merely because its panel was opened.

## Shared device scheduling

Both adapters use one AndroidBridge. A lock covers the entire application switch,
XML read and gesture transaction. Sending holds that lock through recipient/text
verification and outgoing-message verification. The other platform waits its turn.
A cancelled shell task is allowed to finish before the lock is released.

Android applications are brought to the foreground **inside BlueStacks** using a
launcher intent. The Windows cursor is untouched and the Rad.ai panel stays responsive.
This is not simultaneous Android background execution: one app is visible in the
emulator at a time. Network/model generation runs outside the device lock.

The `adb_poll_seconds` interval applies after each platform's scan; actual latency
also includes Android XML dumps, app switches and work by the other platform.
`adb_switch_seconds` is a settling delay after switching Android applications.

Optional service mode: `python main.py --headless --auto-reply`. It hides the Rad.ai
panel, not the Android application requirement. Stop with Ctrl+C. Do not run service
and GUI instances against the same device simultaneously.

## Platform-specific XML configuration

`settings.json` contains two separate selector blocks:

- `selectors`: AnonChat structural selectors.
- `telegram_selectors`: Telegram chat list/rows, title, composer, send, incoming,
  outgoing, back, reply, delete and reply-preview selectors.

A selector can match exact Android XML attributes such as `resource-id`, `text` or
`content-desc`. The built-in `rad-role` and `tg-role` values use structural parsers.
Do not copy Android coordinates into settings; every gesture uses current XML bounds.

Telegram's English accessibility text supplies Sent/Received metadata. The parser
separates it from message text, without inferring direction from bubble position.
Reference: https://github.com/DrKLO/Telegram/blob/master/TMessagesProj/src/main/java/org/telegram/ui/Cells/ChatMessageCell.java

The GUI calls this platform Telegram; the installed Android transport is Vidogram.
Use Existing chat name / Open existing chat for a uniquely named local conversation.
The search excludes global results and rejects duplicate visible names. Known chats
are revisited in rotation. This is not automatic discovery of every account chat.
If visible-list mode is enabled in selectors, private rows are scanned in rotation.
A first visit imports history without answering old messages. Later incoming deltas
trigger automatic replies when enabled. Bot/group/channel rows identified by the
accessibility label are omitted. Unsupported labels stop scanning with a status.
Only visible rows are covered; there is no full-account history API or hidden-list
pagination. Equal visible display names are rejected rather than choosing one.
The Android UI does not supply stable account/message IDs; locally assigned message
IDs and unique visible conversation titles are used within this run. Renaming a chat,
identically named contacts outside the visible list, and missed/scrolled history
cannot be resolved with API-level certainty. Use uniquely named test conversations.

## Existing controls

Auto-reply starts OFF. With it ON, incoming messages schedule generation and AnonChat
searches on recognized home/ended/friend transitions. A supported new anonymous match
gets the fixed greeting before a bio-based opener. Incoming friendship requests are
accepted only when a supported, explicit request control is present.

Start cycle requests one reply with Auto-reply OFF too. Sending manually pauses that
chat. Resume selected restores eligibility. A working chat displays Typing... in the
Rad.ai panel; no network presence/typing API is used. Last five user/assistant messages
are passed to local Ollama (`llama3.2:1b`, `/api/generate`) asynchronously.

Select a message and choose Reply to before manual sending. Delete sent requires a
panel confirmation. Android message actions require a unique visible message and
verified menu/quote controls. Unexpected delete confirmation dialogs are left for
manual inspection; the program does not guess deletion scope. Live reply/delete and
friendship controls still require confirmation against the installed Android layouts.

AnonChat Friends and Past matches retain conversations for the current run. Open a
saved AnonChat friend chat inside Android before operating on it. Telegram can open a
known, uniquely named conversation using local Android search automatically.

Both adapters preserve existing Android drafts and verify written text before sending.
ADB input currently supports printable ASCII only, without a literal `%s`. Unsupported
text is rejected before input. An uncertain submission is paused without blind resend.
After inspecting and resolving an uncertain Android operation, restart Rad.ai to create
a clean baseline. A temporary XML read failure does not permanently disable polling.

Switching to ADB does not remove Telegram's account-level restrictions. This release
changes the transport; it does not implement restriction bypass or automatic retries.

## Validation and private files

See VALIDATION.md for tested behavior and remaining live checks. Runtime diagnostics
and old private state stay in ignored `runtime/`; no credentials, sessions, or customer
XML are included in the release ZIP. Historical releases are backups, not dependencies
of the current application.


## Android transport details

The Telegram tab uses Vidogram Android. Internal chat keys and telegram_selectors
are retained for compatibility. The installed home list does not expose names in
XML, so scan_chat_list is false and local search is used to reopen known chats.
Named local results must be unique; global results are never opened automatically.
All selectors are package-scoped. Explicit launcher activities in adb_activities
were read from the installed package manager. Send taps use the exposed part of
the button bounds outside the overlapping message editor.

## v0.2.9 stability and appearance

The shared device scheduler gives each monitored app a 12-second focus window,
checks actual Android foreground state, and reuses existing activities. Repeated
failures back off (5 seconds up to 60 seconds). Launch cooldown is 8 seconds. A
cross-process device lease rejects a second new controller for the same device.
Close older releases first: they do not implement that lease. System permission
prompts pause navigation until you respond manually.

The Light palette uses white, peach and blush; Dark uses charcoal and purple.
All widgets, dropdowns and dynamically created chat buttons share the same theme.
The transparent pink logo appears in the header; the paw is the window/launcher icon.
Light mode includes small, widely spaced blush paw silhouettes behind the message bubbles, plus paw trails. Asset provenance is in assets/README.md.

## Telegram online presence

There is no keep-online API or synthetic network typing action. XML inspection
requires Telegram/Vidogram to be foreground inside Android, which can make the
account appear online. Auto-reply OFF stops automatic replies, not monitoring.
Use Stop monitoring in the Telegram tab to stop its polling and put it in the
background if it is still foreground. Closing Rad.ai also backgrounds Telegram
when possible. Other sessions and Telegram's own presence delay can still affect
online status. Offline/invisible operation while actively reading via ADB is not
guaranteed; no account privacy settings are changed.
