# Rad.ai v0.1.11

Rad.ai is a local text assistant for AnonChat and Telegram conversations. The
Telegram tab controls Vidogram Android; both platforms use the same BlueStacks
ADB connection. The panel uses CustomTkinter, while Android operations and local
Ollama generation run on an asynchronous worker.

This release does not use Telethon, Telegram Bot API, desktop screenshots, OCR or
Windows mouse automation. It does not include image generation, media sending,
video calls, payments or model training.

## Setup

Keep the release folder intact and close older Rad.ai instances before starting.
Open **Rad.ai.exe** or **Start.cmd**. The EXE is a launcher, not a bundled Python
installation: it uses this folder's `.venv`, or the project environment two folders
above a packaged release.

For a new installation:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Enable Android debugging in BlueStacks and start the local ADB server. The supplied
`settings.json` targets `127.0.0.1:5585` through the ADB server on port `5037`. Change
the device address to the one shown by your BlueStacks instance if needed. Install
and sign into these Android apps yourself, keeping their interface in English:

- AnonChat: `io.anonchat`
- Vidogram: `org.vidogram.messenger`

Rad.ai uses those existing Android sessions. There are no API ID/hash, login-code,
QR or telephone-number fields in the panel. Opening the panel alone does not
connect to either platform or send a message.

Install and run Ollama locally, and download the configured model:

```powershell
ollama pull llama3.2:1b
```

The default endpoint is `http://localhost:11434/api/generate`. If Ollama is not
already running, start its service before generating replies. The model name and
endpoint are configurable in `settings.json`.

## Start an AnonChat conversation

Click **Start AnonChat** once. This selects AnonChat, connects to BlueStacks,
enables Auto-reply and starts or continues partner matching. The button is disabled
while startup is pending, so repeated clicks do not launch duplicate startup jobs.

A recognized new match receives the fixed `hii :3` greeting without waiting for the
LLM. The local model then handles incoming messages or prepares a short opener using
the visible bio. It has not been trained on the owner's conversations. Android
transitions, XML reads and model generation still take time; the control panel stays
responsive during this work.

The AnonChat sidebar has two sections:

- **New partner** contains the current temporary conversation only. Header parsing
  and conversation continuity checks keep messages and bio changes from becoming
  new contacts.
- **Friends** retains a conversation after a recognized friendship transition. The
  same chat key and transcript move here under the person's visible name; the
  temporary conversation is not duplicated.

If either participant closes a conversation before becoming friends, Rad.ai removes
that temporary chat. If it was selected, the panel displays **Chat closed** and
clears the transcript, message selection, draft and reply target. A closed temporary
conversation does not remain in a Past matches section.

With Auto-reply enabled, supported closure and friendship transitions can continue
matching. **Search partner**, **Next partner** and **End chat** provide explicit
controls. Supported incoming friendship requests can be accepted automatically;
unknown or ambiguous Android controls are left for manual inspection. Open an
existing friend conversation inside AnonChat before operating on it from the panel.

## Telegram conversations and matching a person across platforms

Select the Telegram tab and click **Connect Telegram (ADB)**. Open a uniquely named
local conversation in Android, or enter its visible name under **Existing chat
name** and click **Open existing chat**. Known conversations are revisited while
Telegram is the selected platform. A first visit imports visible history without
replying to old messages; later incoming changes can trigger Auto-reply.

To connect a person you invited manually from AnonChat:

1. Select their AnonChat conversation and click **Link to Telegram**.
2. Ask that person to send the displayed code as a message on its own in Telegram.
3. Open their Telegram conversation in Rad.ai so the incoming code can be read.

The code is valid once for 10 minutes. A verified code links the person's identity
and up to five recent context entries while keeping the platform send routes
separate. No invitation or code is sent automatically, and matching display names
never establish identity. The handoff keeps a context snapshot if the temporary
AnonChat conversation closes before the code arrives. Codes, links and conversation
memory are session-local; restarting Rad.ai clears them.

## Replies, manual control and uncertain sends

Auto-reply starts OFF when the panel opens. **Start AnonChat** explicitly turns it
ON. The switch can turn automatic replies off at any time; a submission already
underway cannot be undone.

Incoming bursts wait for a 3-second quiet period, with a 10-second collection cap.
Messages arriving while the model generates a reply are queued for the following
response rather than restarting or discarding the current generation. A completed
reply waits if its platform is no longer selected. Manual takeover, a closed chat or
turning Auto-reply OFF can still invalidate unsent work.

- **Start cycle** requests a reply to waiting incoming content even with Auto-reply
  OFF. It does not invent a reply when there is no incoming message to answer.
- **Send manually** pauses that conversation. **Resume selected** makes it eligible
  for automatic replies again. Drafts are kept separately for each selected chat.
- **Typing...** indicates active work in the Rad.ai panel; it is not a synthetic
  Telegram typing or online-status API action.
- **Reply to** targets a selected visible message. **Delete sent** asks for panel
  confirmation before attempting a supported Android deletion action.
- **Check send** re-reads Android history for an uncertain submission. It never
  resends. A uniquely verified outgoing occurrence clears the uncertainty and leaves
  the chat paused for review; missing or ambiguous evidence keeps it paused.

The last five user/assistant context entries are passed to local Ollama. Each reply
is routed through its own conversation identity checks. If continuity or the current
recipient cannot be established, the action pauses instead of guessing.

Existing Android drafts are preserved. ADB text input currently supports printable
ASCII only and does not accept a literal `%s`. Unsupported text is rejected before
input. Android reply/delete menus require a unique visible message and recognized
controls; unfamiliar confirmation dialogs are left for inspection rather than
assuming a deletion scope.

## Device focus and background operation

The GUI monitors its selected platform. Selecting Telegram leaves AnonChat polling
and pending automatic replies waiting; selecting AnonChat does the reverse. An
already-started send retains the shared device lock through verification before
another action can use Android. XML reads, application switches and gestures are
serialized to avoid two adapters controlling the same screen at once.

Android applications must be foreground **inside BlueStacks** to expose their XML.
The Windows cursor is not moved, but this is not simultaneous hidden execution of
two Android apps. LLM generation runs outside the device lock.

Actual foreground state is checked before launching an app. Existing activities are
reused, rapid relaunches have an 8-second cooldown, and repeated failures back off
from 5 to 60 seconds. A device lease rejects another current Rad.ai controller for
the same emulator. Older releases may not implement that lease, so close them first.
Android permission dialogs pause navigation until you handle them manually.

A service mode is available:

```powershell
.\.venv\Scripts\python.exe main.py --headless --auto-reply
```

It hides the Rad.ai panel, not the emulator requirement. Without a selected GUI tab,
monitored platforms use timed rotation with a default 12-second focus window. Stop
with Ctrl+C; do not run GUI and service instances against the same device together.
Polling latency includes XML dump time, Android transitions and any active send.

## Telegram online presence

There is no keep-online API. Bringing Vidogram to the Android foreground to inspect
messages can make the account appear online. Auto-reply OFF stops replies, not
monitoring. **Stop monitoring** in the Telegram tab stops polling and backgrounds
Vidogram if it is still foreground. Closing Rad.ai also attempts to background it.
Other sessions and Telegram's presence delay can still affect the displayed status.
Invisible/offline operation while actively reading through ADB is not guaranteed;
Rad.ai does not change account privacy settings.

## Configuration and current limits

`settings.json` contains separate `selectors` for AnonChat and `telegram_selectors`
for Telegram. `rad-role` and `tg-role` entries use package-scoped structural XML
parsers; explicit selectors can match Android attributes such as `resource-id`,
`text` and `content-desc`. Gestures use current XML bounds rather than fixed desktop
coordinates. `adb_activities` supplies the installed launcher activities.

The supplied Vidogram home layout does not expose conversation names in XML, so
`scan_chat_list` is false and local search opens known chats. Search excludes global
results and rejects duplicate visible names. There is no full-account history API,
hidden-list pagination or automatic discovery of every conversation. Android XML
does not provide stable Telegram account/message IDs: local message identifiers and
unique visible titles are used within the current run. Renamed chats, identically
named contacts outside the visible results and missed or scrolled-away history can
therefore require manual inspection.

Friendship, closure, reply and deletion controls depend on the installed Android
layout. This release does not claim support for every layout or live verification of
every friendship-acceptance path. See [VALIDATION.md](VALIDATION.md) for the checks
performed and remaining live limitations. Changing to ADB does not bypass Telegram
account restrictions or spam controls.

## Appearance and release files

The bottom-right crescent/sun icon toggles Dark and Light. Dark uses charcoal and
purple; Light uses white, blush and peach, with small, widely spaced paw silhouettes.
The transparent pink paw and Rad.ai wordmark appear together in the header. The
window and EXE use the paw icon. See [assets/README.md](assets/README.md) for asset
provenance.

Runtime diagnostics and private state stay in ignored `runtime/`. Release ZIPs must
exclude private XML, credentials and session files. Historical release folders are
backups, not dependencies of the current source.
