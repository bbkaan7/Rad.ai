# Latest validation

## Automatic conversation update — 2026-10-02

76 tests passed with mocked desktop input, including generation-time arrivals,
recipient changes, preserving earlier messages in a group, cached bubble reads,
two-stage model calls, invalid plans, per-part history commits, uncertain second
parts and cancellation when new incoming text arrives between parts.

A synthetic local Ollama request successfully produced a reply using the planner
and writer. This checks integration, not conversation quality.

Reference-search replay on a Telegram fixture measured 0.273 seconds cold and
0.008 seconds with the discovered scale cached. These are individual lookup timings,
not end-to-end application latency. LLM and typing delays were not changed.

The updated panel opened with the four manual controls removed. No messages were
sent in this update. Live burst reception and multi-bubble sending remain unverified;
keep auto-send off until supervised testing is satisfactory. Scanning is foreground
only and message grouping is limited to visible text bubbles. Changes during typing
still require inspecting the unsent draft.

# Validation — Rad.ai 0.2.4

Date: 2026-10-02

## Automated regression checks

68 tests passed, no skips, in the existing Windows Python environment. Desktop
input and clipboard calls in unit tests are mocked. Coverage includes conversation
isolation, stale/duplicate reply rejection, manual reconciliation, pause, rewrite,
greetings, guarded sending, exact-draft recovery, clipboard freshness, moving-window
rejection, negative screen coordinates, DPI/dock behavior and OCR preprocessing.

New automatic-calibration tests cover surface discovery, advertisement exclusion,
multi-scale reference matching, ambiguous-reference rejection, divider detection,
bounded header extraction, empty panes, bubble-color learning, clearing stale chat
regions, unique OCR labels, label search bounds and rejecting ambiguous fallbacks.

## Local image replay

Three previous native captures (Anonchat home, Anonchat friend chat, Telegram chat)
were recognized from profiles with no saved regions or bubble colors. All nine
resized variants at 0.8x/96 DPI, 1.2x/144 DPI and 1.5x/180 DPI were recognized.
Both Anonchat captures also passed after removing the advertisement dock. The
current 455x782 Anonchat home capture passed after the fine-scale and label fix.
These are image-replay checks, not physical multi-monitor tests.

## Live checks for this revision

- Rad.ai.exe launched the panel; the supplied paw appears in the header and title
  icon. Restart loaded the latest code and retained the version label 0.2.4.
- Auto-calibrate recognized the current Anonchat home screen without manual
  region selection and reported `Automatic calibration complete: home`.
- Telegram with no selected chat stopped with an instruction to open a private
  chat. After opening the designated test chat, automatic calibration reported
  `Automatic calibration complete: chat` without manual region selection.
- Experimental auto-send remained unchecked. No new messages were sent in this
  revision's calibration tests.

## Evidence inherited from v0.2.0

The previous release exercised local generation/rewrite, Telegram Copy Text,
approved sends on Telegram and Anonchat, Anonchat matching and watch-preview.
The user confirmed physical F10 pauses input. Those checks are historical evidence;
the full send flow has not been repeated after this calibration rewrite.

## Limits

- This is a supervised single-chat alpha, not an unattended service.
- Physical mixed-DPI multi-monitor use and sustained auto-send remain unverified.
- Theme changes, unsupported layouts, overlays or tiny text can stop recognition.
- Headers are visual change detectors, not platform account IDs. Rebind after
  changing recipients or resizing; do not rely on visually identical names.
- OCR and the small local model can make mistakes. Review incoming text and drafts.
- Seeing an outgoing bubble proves visible submission, not server delivery.
- Live greeting submission and the new pending-send recovery UI remain unverified.
- Target apps must be open and signed in. No unattended login/account recovery,
  persistent customer memory or parallel-chat scheduler is included.

Diagnostic capture is disabled. Source screenshots stay in the local work area
and are excluded from the release archive.
