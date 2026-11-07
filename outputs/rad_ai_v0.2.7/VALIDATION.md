# Rad.ai 0.2.7 — Telegram ADB migration validation

- 45 unit/regression tests passed.
- Source compiles and the application imports with Telethon uninstalled.
- pip check: no broken requirements.
- GUI smoke test passed: both themes, message rendering, four sidebar sections,
  shared ADB bridge identity, and no QR dialog. No account connected during this test.
- Device arbitration tests cover whole-transaction locking and cancellation while
  an ADB shell thread is still working, foreground mismatch and package validation.
- Telegram XML tests cover chat list discovery, Sent/Received parsing, history
  baselining, subsequent incoming messages, round-robin scanning, duplicate names,
  existing drafts, recipient changes and verified outgoing messages using fixtures.
- The installed org.telegram.messenger package was detected on 127.0.0.1:5585.
  Its actual welcome XML was inspected read-only. Android sign-in was not complete.
- The owner is completing Android sign-in. The device subsequently disconnected;
  authenticated live chat selectors and cross-app live cycles remain unverified.
- No live message was sent or deleted. Reply/delete controls remain conditional on
  supported, uniquely identified XML menu/quote elements and verified outcomes.
- Existing UI layout and version 0.2.7 were retained. Telegram's connection button
  now reads Connect Telegram (ADB). Login/API credential code was removed.
- Private runtime state is excluded from the release ZIP.
