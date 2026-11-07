# Rad.ai v0.2.6 validation

82 offline tests pass with desktop input mocked. Six new checks cover one-time
match claims, excluding existing/Telegram conversations, fixed greeting before
bio/Ollama, no model call after an uncertain greeting, labelled bio extraction,
and recipient-change rejection. The first outgoing text is exactly hii :3.

The inherited suite covers burst refresh, two-stage replies, per-part history,
visual matching, OCR, pending-send recovery and pause/focus guards.

Live fixed-greeting and bio-opener sending have not been tested. Bio OCR is limited
to labelled text visible above message bubbles; unavailable text uses a generic
opener. Matching identities are visual headers rather than platform account IDs.
Polling is 500 ms while waiting, plus actual capture/matching/UI time. There is no
measured end-to-end greeting latency guarantee. Unknown layouts, changes during
typing or an uncertain send still stop for inspection.

Physical mixed-DPI multi-monitor operation, sustained unattended operation and
live multipart sending remain unverified. One foreground chat and one app instance.
