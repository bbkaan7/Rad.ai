# Rad.ai v0.2.4

Local, supervised text assistant for English Anonchat in BlueStacks and normal
Telegram Desktop private chats. No Bot API or Telegram Business API is used.

## Start and use

Open Rad.ai.exe or Start.cmd. Both use the existing Python environment under
%USERPROFILE%\Desktop\sohbet_alpha\.venv. Tesseract with English data and Ollama
with the selected model must already be installed. This is not a standalone installer.
Open and sign in to the target app yourself.

Select Anonchat or Telegram. Rad.ai automatically calibrates and binds the open
conversation. There are no Bind, Read, Generate or Auto-calibrate buttons. Anonchat
Search for partner and Next partner remain available. A home screen waits for an
active chat; no partner search is initiated automatically.

Keep the target app in the foreground while waiting for messages. Reading and
drafting run automatically. When you switch to Rad.ai to edit a draft or use another
app, background scanning yields control instead of stealing focus. Select the
platform again to resume after Pause or F10. Unknown layouts and focus changes stop
input. The corner fail-safe remains enabled.

## Incoming groups and two-stage replies

Consecutive visible incoming text bubbles after the latest visible outgoing bubble
are collected in order. [NEXT_INCOMING] indicates the boundary between received
messages. The first model call plans whether to answer the group together or handle
distinct questions separately. The second writes one to four natural reply bubbles.
The local model is unchanged; two-stage generation uses two model calls per attempt.

If messages arrive during generation, the obsolete draft is discarded and generation
repeats using the refreshed group. After eight consecutive changes it stops rather
than looping indefinitely. Visible text only is supported; messages scrolled out of
view, media-only messages, repeated identical text and OCR errors remain limitations.

[NEXT_MESSAGE] separates outgoing bubbles in the editable draft. It is never sent
as message text. Review all parts, then choose Send reviewed reply. Each part is
submitted and checked separately. Only verified parts enter temporary history.
New incoming text between outgoing parts cancels the unsent remainder so the next
draft can respond to the new text. An uncertain send stops and requires reconciliation.
Changes during typing still stop with the partial draft left for inspection.

If incoming text changed before a reviewed send, a new draft is prepared for review.
Experimental auto-send is OFF by default; enabling it sends prepared groups without
another review. It stops after ten completed/partially completed groups. This is not
validated for unattended production operation.

Rewrite reply revises an unsent draft. Finish pending send only submits an exact
visible pending draft; it never types a second copy. Inspect the target before using
Confirm delivered or Not sent / draft cleared. A visible outgoing bubble proves UI
submission, not server delivery or reading.

## Performance and calibration

The driver retains the current calibration across actions. Size/DPI changes trigger
a rescan. Reference images and discovered matching scales are cached; controls are
still located on the current image, not clicked at stale saved coordinates. Repeated
lookups in one capture and OCR of unchanged bubble images reuse results. Typing speed
and the existing model are unchanged.

Supported reference layouts are English Anonchat's light interface and the tested
Telegram Desktop interface. Unknown themes, overlays or very small windows may stop
recognition. Physical mixed-DPI multi-monitor operation remains unverified. Visual
headers detect changes but are not stable account IDs. One foreground chat at a time.

Telegram Copy Text reading replaces the Windows clipboard. Conversation context is
temporary and resets on platform changes/restart. Debug captures are disabled.
No persistent customer memory, persona training or media sending is included.

See VALIDATION.md for test evidence. Run python -m unittest discover -s tests -q
for offline tests with mocked desktop input. Review OCR and model output: the small
test model can misunderstand messages or invent details.
