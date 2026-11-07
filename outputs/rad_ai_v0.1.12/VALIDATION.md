# Rad.ai v0.1.12 validation

- 138 unit/regression tests pass, including the v0.1.11 lifecycle/routing suite.
- Added informal question intent, older-question physical Reply targeting, separate
  handling of the later question, per-chat isolation and uncertain-send boundaries.
- Synthetic Android transaction tests execute long-press, Reply, quote checking,
  text input and Send for both AnonChat and Telegram adapters. Missing quote previews
  stop submission; a normal message bubble cannot substitute for a quote preview.
- Request tests cover clickable parent/child labels, headerless dialogs, auto-off,
  outgoing/unrelated/spoofed labels, ambiguity, failed confirmation with no repeat
  tap, and accepted friendship preserving the same chat/history.
- Diagnostics tests inject chained errors and inspect real temporary log files:
  original lines and local counters, redaction, nested correlation, concurrent
  writes, bounded rotation, cancelled tasks, async failures, disk failure and step
  history limits. Test data is synthetic; release archives exclude all runtime logs.
- Dependency check passes. Version is 0.1.12; Windows launcher uses 0.1.12.0 metadata.

No new third-party messages or friend requests were sent for this release. Android
transaction tests use synthetic XML and mocked ADB transport. Actual incoming-request
and Reply layouts still depend on the installed Android app; a fresh cross-account
live acceptance/reply test has not been completed in this pass. The English intent
grammar is heuristic. Tests are not a zero-bug or unattended-production guarantee.
