# Validation — 0.2.0 supervised alpha

Date: 2026-10-01

## Automated checks

52 tests passed in the project's Windows Python environment, with no skips.
Desktop input and clipboard access in these tests are mocked.

Coverage includes conversation isolation, stale and duplicate reply rejection,
manual reconciliation, pause during generation, rewrite cancellation/failure,
opening greetings, guarded Enter/button submission, exact-draft recovery,
template ambiguity, negative monitor coordinates, moving-window rejection,
bubble selection, clipboard freshness, DPI/dock calibration preservation,
adaptive chat-pane height and dark-bubble OCR preprocessing.

## Live checks completed

- English panel opens through DesktopAssistant.exe; Restart reloads the app.
- Tesseract runs and local Ollama llama3.2:1b generates and rewrites drafts.
- Telegram Desktop reads exact incoming text through its normal Copy Text menu.
- With specific user approval, the panel sent "Thank you for the test message"
  to the designated Telegram test contact. The outgoing text matched and
  temporary context was committed automatically.
- Anonchat Next partner found its reference and bound a new match. Search for
  partner also opened a new match after its reference was recaptured at native DPI.
- The active-input guard blocked ended chats; the advertisement dock was excluded.
- In the user-prepared Anonchat friend chat, the expanded message pane read "Hot?"
  correctly. Watch mode, with Auto-send OFF, generated one draft and stopped.
- Anonchat Enter inserted a newline instead of sending. The first approved test
  was completed with a manual Send click, then the profile was changed to a visual
  Send-button reference. A second approved message, "Thanks for helping with the
  test.", was typed and sent entirely through the panel using that reference.
- Outgoing OCR initially added a border artifact and correctly required manual
  reconciliation. After the preprocessing fix, the already sent message matched
  exactly from the app's native 830x928 capture, without another transmission.
- The user confirmed that physical F10 displays "Paused". Synthetic F10 from the
  control tool did not trigger it; physical and synthetic input are not equivalent.

These observations prove UI submission, not server delivery or recipient reading.

## Remaining limitations and experimental checks

- The final outgoing OCR correction passed replay on a native captured frame;
  the complete post-fix automatic commit path has not been repeated with a new send.
- Greeting rules and local generation passed; live greeting submission is untested.
- Finish pending send has exact-text and conversation-guard regression tests;
  live recovery using that new button has not been exercised.
- Automatic multi-reply Watch mode has not passed sustained live testing.
  Auto-send remains off by default and should be treated as experimental.
- Short-message OCR is imperfect; one "Hi" sample was read as "Ht". Review output.
- The lightweight model can produce irrelevant or invented details. Persona
  training and production model evaluation are not part of this release.
- Physical mixed-DPI multi-monitor operation and arbitrary resizing are unverified.
- Visual headers are change detectors, not stable account IDs. Identical cropped
  headers can be indistinguishable. Rebind when switching conversations.
- Target applications must already be open and logged in. There is no unattended
  startup, account recovery, multi-customer scheduler or persistent customer memory.

This release covers the supervised single-chat MVP. Diagnostic capture is OFF;
calibration sources and native test captures are retained in the local work area,
not bundled as chat-history artifacts in the application folder.
