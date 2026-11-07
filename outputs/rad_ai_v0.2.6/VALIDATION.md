# API/ADB v0.2.6 validation

17 offline tests passed, using synthetic XML and mocked network/device sends.
Coverage: five-message context isolation, duplicate occurrences, XML bounds,
shell quoting, unsupported Unicode, burst updates during generation and sending,
manual takeover, global auto-off, uncertain send rejection, historical-event
suppression, typed-text verification and changed-recipient rejection.

The isolated environment passes pip check. All new modules compile and import.
A real async aiohttp call to local Ollama /api/generate returned a text reply.
The new Rad.ai v0.2.6 window appeared in the desktop window list. Visual inspection
was blocked by the desktop tool reporting that the window no longer belonged to
the same reported application identifier. No visual verification is claimed.

Live Telegram authentication and AnonChat XML selectors have not been configured.
No live account messages were sent. ADB match lifecycle, online presence and typing
indicators need account/device integration testing after local setup.

The active distribution contains no legacy screen/OCR adapters or dependencies.
Previous screen-based files are retained only in a local work-area backup.

QR/XML update: 24 tests passed. Live ADB XML from io.anonchat verified incoming text, bio, input and partner controls. QR refresh/cancel tested with mock tokens. No live QR authentication or outgoing messages performed.
