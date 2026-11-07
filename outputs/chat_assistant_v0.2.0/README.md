# Desktop Assistant — v0.2.0 supervised alpha

Normal Telegram Desktop private chats and Anonchat in BlueStacks, with a local Ollama model. All application text is English. No Bot API, Telegram Business, payment integration, persona training or media sending is included.

This release is for one foreground conversation with operator review. Its tested
path is read, draft, optionally rewrite, review and send. Unattended operation is
outside the release criteria; automatic sending remains experimental and off by default.

## Start

Double-click **DesktopAssistant.exe** for the panel without a terminal, or **Start.cmd** to see startup errors in a terminal. Both use the existing Python environment under `%USERPROFILE%\Desktop\sohbet_alpha\.venv`. Ollama must be running with the selected model installed. Tesseract requires English language data. Use **Check setup** to check both services without sending anything.

For a separate environment, install `requirements.txt` and run `python main.py`. The target applications should already be open and signed in. Login remains manual.

## Read, generate, rewrite and send

1. Select the platform, open the intended conversation, and click **Bind current chat**.
2. Check the incoming text, then select **Generate reply**.
3. Edit the draft manually or click **Rewrite reply**. Give an instruction such as `Shorter` or `More friendly`. A blank instruction requests different wording. Cancel leaves the draft unchanged.
4. Select **Send reviewed reply** when ready. The target and incoming message are checked again before sending.
5. The assistant checks for the outgoing message. If verification is uncertain, inspect the real conversation and resolve the result before retrying. Clear any unsent partial draft manually before choosing **Not sent / draft cleared**.
6. Read the next incoming message to continue. Bind again after switching recipients.

If a send stopped with the full draft still visible, **Finish pending send** can
submit it without typing a second copy. This is currently calibrated for Anonchat.
The visible draft must match the pending reply exactly, and the recipient and
incoming message are checked again. Partial or uncertain OCR text blocks recovery;
inspect and handle it manually. Never use recovery when an outgoing bubble already
shows that message.

For an empty newly bound chat, **Draft greeting** prepares an opening message. Review and send it using the same controls. If an incoming message arrives before sending, the greeting is blocked so you can read and reply to it instead. Greeting drafts do not invent customer messages in the conversation history.

Rewriting never sends a message or commits unsent drafts to history. A failed rewrite keeps the previous draft; pause discards a late result. The lightweight test model can still generate poor wording. Owner-style training belongs to v0.3.0.

An outgoing bubble confirms visible submission, not server delivery or recipient reading. Temporary history is reset by rebinding, changing platforms or calibration, and restarting.

## Matching and watching

**Search for partner** and **Next partner** use calibrated visual references. The assistant waits up to 30 seconds for an active chat after clicking. It does not assess bios, accept friend requests, invite people to Telegram or cycle through strangers autonomously.

**Watch current chat** requires message-pane, incoming-bubble and active-input calibration. With **Auto-send** unchecked it generates one draft for review. With that checkbox enabled it actually sends in the bound chat, with a maximum of ten replies per run. Outgoing verification is required; uncertainty stops the run. This sending mode is not enabled by default.

Only the latest incoming bubble is read. Identical repeated messages and bursts have limited handling. Do not treat this release as an unattended production service or a multi-customer scheduler.

## Text reading

OpenCV locates buttons and message bubbles. Anonchat uses Tesseract OCR. Review OCR output for small text, emoji and non-English messages.

Telegram can use the ordinary application's **Copy Text** menu after locating the bubble visually. This avoids OCR spelling and timestamp errors without an account API. **Reading this way replaces the Windows clipboard text.** Previous clipboard contents are not read or retained. Stale clipboard contents and changes during copying are rejected.

## Calibration and monitors

Select an item and choose **Calibrate selected item**, then drag a rectangle on the frozen target image:

- `chat`: message pane, excluding header, chat list, input and ads.
- `incoming_sample` / `outgoing_sample`: one message bubble including its background.
- `identity`: a stable, distinct recipient name or identifier without online status.
- `chat_anchor`: an input-row icon visible only in an active chat.
- `empty_textbox`: the empty input's distinctive placeholder.
- `send`, `search`, `next`: the corresponding controls.
- `searching`, `ended`, `blocked`: optional screen-state references.
- `incoming`: legacy single-message-region OCR mode.

The tested English Telegram Copy Text reference is supplied in `templates/`. Profiles are stored locally in `profiles.json`. Theme, font and layout changes can require new references.

Moving a window without resizing is supported. Movement during a capture or click cancels the operation. Regions and templates account for DPI; an unexpected size stops with a calibration message. The calibrated BlueStacks left advertisement panel is handled separately from its chat viewport. Arbitrary resizing, resolutions and monitor layouts are not guaranteed to work without calibration. Physical mixed-DPI multi-monitor operation has not yet been validated.

Recalibration at another supported DPI or with the known side panel open preserves existing references. A real layout-size change resets incompatible calibration and reports that the remaining items need calibration. A selection inside the recognized advertisement area is rejected.

Header images are change detectors, not verified platform account IDs. Identical cropped headers may not be distinguishable. Use one selected foreground chat at a time.

## Stop and recovery

Press **F10** or **Pause / Take over** to stop subsequent input. PyAutoGUI's corner fail-safe remains enabled. Already typed or sent content cannot be undone. A running model request may take up to its 90-second timeout to return; its result is discarded after pause.

**Restart** reloads the application when idle and no send is unresolved. Run one assistant instance and do not run the older F9 script simultaneously. Startup failures are written to `startup-error.log`.

The optional `debug_capture` setting overwrites one local diagnostic image per platform in `diagnostics/`. It is for integration testing and should be disabled for ordinary use.

## Validation

Run `python -m unittest discover -s tests -v`. These tests use synthetic images and mocked input/clipboard calls, without contacting customers. See `VALIDATION.md` for live testing evidence and the remaining experimental-feature checks. The small local test model can misinterpret brief messages or invent details; review drafts before sending.
