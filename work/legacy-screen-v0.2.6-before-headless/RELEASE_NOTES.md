# Rad.ai v0.2.6

- Removed Draft greeting and the manual empty-chat binding flow.
- New Anonchat matching transitions send the literal hii :3 without an LLM call.
- After verified greeting submission, read the visible labelled bio and send a
  short model-written conversation opener, with a generic fallback for missing bio.
- One opening attempt per detected matching transition; uncertain sends never retry
  automatically. Existing chats on startup and Telegram do not trigger this opening.
- New-chat polling interval reduced to 500 ms between screen operations.
- Existing automatic reading, grouped replies and pause controls remain available.

82 offline regression tests passed. No live greeting or bio-opener messages were
sent as part of this revision's verification. See VALIDATION.md for limitations.
