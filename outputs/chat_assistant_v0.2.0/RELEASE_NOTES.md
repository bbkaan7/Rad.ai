# v0.2.0 — supervised alpha

- Normal Telegram Desktop private-chat adapter, without Bot API or Business API.
- Anonchat matching and single-chat reading/replying through BlueStacks.
- Local Ollama draft generation, editable replies and Rewrite reply instructions.
- Draft greeting for a newly bound empty conversation.
- Manual sending with recipient/message rechecks and outgoing verification.
- Finish pending send checks the visible draft before submitting without retyping.
- Watch-preview mode prepares one draft; automatic sending remains experimental.
- F10 and the Pause button stop subsequent input.
- Window-relative coordinates, DPI-aware calibration and a known BlueStacks dock.
- Input-anchor-based message-pane height for Anonchat friend conversations.
- English application text, local settings and no saved conversation history.

52 automated tests passed. Both platforms were used for approved live test sends.
See VALIDATION.md for precise evidence and limitations, including OCR/model quality,
untested sustained automatic operation and physical multi-monitor coverage.

Open DesktopAssistant.exe or Start.cmd. Existing app logins and the local Python,
Tesseract and Ollama setup are required; this package is not a standalone installer.
