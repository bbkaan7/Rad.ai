# Rad.ai v0.2.4 — automatic conversation update

- Platform selection calibrates and binds the current chat automatically.
- Removed manual Bind, Read, Generate and Auto-calibrate buttons.
- Added automatic incoming-message reading and draft generation while the target
  application is foreground; manual review remains the default sending mode.
- Group consecutive incoming text bubbles and refresh drafts when new text arrives
  during model generation.
- Added separate model planning and writing stages, with one to four outgoing bubbles.
- Verify and commit each outgoing part separately; stop uncertain sends and cancel
  unsent parts if a new incoming message arrives between parts.
- Reuse calibration, reference scales and unchanged bubble text to reduce overhead.
- Retained Rad.ai branding, the paw icon, F10/Pause and the existing typing speed.

76 offline tests pass. Two-stage generation passed a synthetic local Ollama smoke
test. Live multipart sends were not performed during this update.
