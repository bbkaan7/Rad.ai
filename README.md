# Rad.ai v0.1.15

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

Install the included **android-helper/rad-bridge.apk** in BlueStacks, or click
**Android bridge** in Rad.ai while both monitors are stopped. Open **Rad.ai Bridge**
in Android and enable its Accessibility service and Notification access using its
two settings buttons. The owner must enable these permissions; the application
never changes permission settings automatically. Return to Rad.ai and connect.

The helper serves only allowed app data on Android localhost port 8765. A protected
ADB-shell pairing provider supplies a per-install credential, and authenticated
forwarding uses desktop localhost port 18765. No platform API credentials are used.
BlueStacks can expose the same instance as `emulator-5584` instead of
`127.0.0.1:5585`; Rad.ai accepts this exact port-pair alias, not an arbitrary device.
See **android-helper/README.md** for source/build and removal instructions.

Install and run Ollama locally, and download the configured model:

```powershell
ollama pull llama3.2:1b
```

The default endpoint is `http://localhost:11434/api/generate`. If Ollama is not
already running, start its service before generating replies. The model name and
endpoint are configurable in **Settings** or `settings.json`. The owner's existing
model is preserved when updating the application.

## v0.1.15 hotfix

- Settings: model/endpoint, LLM timeout (default 300 seconds), message collection
  delay, waiting-draft delay/pace and fixed greeting. Save applies to the next reply
  without restarting; wait for an active reply to finish before saving.
- After five seconds of generation, random temporary text changes slowly in the
  verified foreground conversation. It is never submitted. Only unchanged bot-owned
  text is cleared on completion or timeout. Manually edited drafts are preserved.
- The updated helper inserts the final reply in one editor action, including Unicode.
  Older helper builds retain the restricted ASCII ADB input path.
- Telegram accessibility polling stays in the open chat. Notification navigation
  waits for active reply jobs; idle polling no longer rotates through chats.
- Empty new matches observed before Auto-reply starts keep their pending fixed
  greeting. Existing conversations and friends are not greeted again.
- Ollama timeouts are distinguished from Android failures. Uncertain submissions
  and timed-out model requests are never blindly retried.

Do not press Android Send while temporary typing text is present. If you edit it,
Rad.ai keeps your changes and pauses. Clear the Android input and use Start cycle
when ready. Auto-reply OFF cancels generation and cleans its draft, but cannot undo
an already submitted message. Connection loss may require inspecting a leftover draft.

## Start an AnonChat conversation

Click **Start AnonChat** once. This selects AnonChat, connects to BlueStacks,
enables Auto-reply and starts or continues partner matching. The button is disabled
while startup is pending, so repeated clicks do not launch duplicate startup jobs.

A recognized new match receives the fixed `hii :3` greeting without waiting for the
LLM. The local model then handles incoming messages or prepares a short opener using
the visible bio. It has not been trained on the owner's conversations. Android
transitions, accessibility reads and model generation still take time; the control panel stays
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
unknown or ambiguous Android controls are left for manual inspection. Click a saved friend in Rad.ai to reopen the visible matching row and verify its history. Incoming notifications also route back to known friends. Temporary conversations remain separate during those visits.

## Telegram conversations and matching a person across platforms

Select the Telegram tab and click **Connect Telegram (ADB)**. Open a uniquely named
local conversation in Android, or enter its visible name under **Existing chat
name** and click **Open existing chat**. Accessibility reads the open conversation immediately. Background notification previews appear in the Telegram tab; Rad.ai opens and verifies the associated conversation before importing new messages. A first visit imports visible history without
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
reply waits for the shared Android transaction lock and rechecks its recipient. Manual takeover, a closed chat or
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

Both connected platforms remain monitored regardless of the selected panel tab.
Android AccessibilityService events wake the foreground reader; no `uiautomator
dump` is used with the supplied settings. NotificationListenerService delivers
background message previews to a separate sidebar area, even while another app is
visible. Previews are not inserted into LLM context: the full conversation is opened
and its header/history verified first. Group notifications are not routed to private
chats. Duplicate notifications are coalesced. Existing drafts and in-flight sends
prevent navigation until the transaction is safe to leave.

This does not expose both inactive Android view hierarchies at once. Silent/muted
notifications, hidden message previews and inaccessible custom views can require
opening the conversation manually. The default reader does not continually switch
apps merely to poll. Connections, requested actions and notification verification
can bring an app forward inside BlueStacks. Windows mouse position is unchanged.
LLM generation runs outside the shared Android lock.

A service mode is available:

```powershell
.\.venv\Scripts\python.exe main.py --headless --auto-reply
```

This hides the Rad.ai panel, not the Android requirement. Stop with Ctrl+C and do
not run the GUI and service against the same emulator together. The device lease
rejects competing controllers. `accessibility_enabled: false` selects the older XML
reader for troubleshooting only; there is no silent fallback when the helper is
missing or its permissions are disabled.

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
for Telegram. `rad-role` and `tg-role` entries use package-scoped structural
selectors on an in-memory accessibility tree; explicit selectors can match Android attributes such as `resource-id`,
`text` and `content-desc`. Gestures use current accessibility bounds rather than fixed desktop
coordinates. `adb_activities` supplies the installed launcher activities.

Some Vidogram home layouts do not expose conversation names even through accessibility.
`scan_chat_list` is false and local search opens known chats; readable rows on first
connection are listed immediately. An unreadable list is not reported as an empty account. Search excludes global
results and rejects duplicate visible names. There is no full-account history API,
hidden-list pagination or automatic discovery of every conversation. Android accessibility
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


## v0.1.12: requests, question replies and diagnostics

With Auto-reply ON, recognized incoming AnonChat friendship requests are accepted.
Accept text may be on a child label inside a clickable Android view, including a
request dialog without a chat header. Transcript/bio content and outgoing request
notices are excluded. Multiple ambiguous Accept controls are not guessed. A pending
acceptance is not tapped repeatedly; normal friendship confirmation moves the same
conversation into Friends. Auto-reply OFF leaves requests under manual control.
Labels can be adjusted in selectors.friend_requests in settings.json.

An English question-intent grammar recognizes WH questions, auxiliary questions,
indirect requests and common chat abbreviations such as wyd/hbu, including messages
without question marks. This is a lightweight heuristic, not a trained intent model;
ambiguous phrasing can be misclassified. It adds no additional LLM request.

When two adjacent unanswered incoming messages are both questions, the older one
becomes the physical Reply target. The model answers that question first; the later
question remains queued for its own response. Already handled messages, another
person's messages and pairs separated by an outgoing message do not trigger this
rule. For longer runs of questions the oldest qualifying pair is handled first.
Android long-press, Reply selection and the quote preview are verified; a missing
or changed quote pauses sending rather than silently sending an unquoted answer.

Use **Open error log** in the footer to open runtime/rad_error.log. Each record has
UTC time, version/build/settings fingerprints, run/process/operation IDs, failure
stage, error type/message, chained traceback locations, frame-local variable names
and safe summaries, and the last 30 steps of the operation. A numeric counter or
phase is retained; message bodies, arbitrary object contents and credentials are
not dumped. Context strings are redacted/summarized and conversation keys hashed.
The logger cannot infer which variable semantically caused a bug; the recorded
frame/state and call chain are evidence for diagnosing it.

The active log rotates at 5 MB with three backups (.1, .2, .3). Send the current log
and any rotated file covering the time of the problem, plus the approximate time
and button/action you used. See HOTFIX.md. Logs stay local and are excluded from
release ZIPs. Background polling and GUI callbacks catch and log failures; uncertain
sends pause without blind retries. Fatal startup failures can still require fixing
configuration or dependencies before restart. No Python logger can record a power
loss, forced process termination or a failure before Python itself starts.
