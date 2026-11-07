# Rad.ai v0.1.11 validation

Validated on 2026-10-04. The release number was explicitly changed from the planned
v0.2.10 to v0.1.11 at the owner's request; the hotfix scope was retained.

## Completed checks

- 111 unit/regression tests pass. They cover XML identity parsing, grouped
  messages, friendship promotion preserving chat identity/history, temporary-chat
  deletion and stale callback suppression, handoff after source deletion, incoming
  bursts during generation, greeting priority, reply reconciliation boundaries,
  changed recipients, same-title Telegram quarantine, selected-platform scheduling,
  launch pacing, and offline ADB recovery without replaying commands.
- Local CustomTkinter integration checks pass: theme toggle, logo alpha and ICO
  sizes, Start AnonChat duplicate-click suppression, synchronized Auto-reply switch,
  New partner/Friends sections, same-key relocation, closed-chat removal, isolated
  drafts and background updates that do not change the selected platform.
- Replayed 59 previously captured private AnonChat XML snapshots. There was never
  more than one active temporary conversation, and closed nonfriends were removed.
  Repeated XML from an existing friend with historical acceptance notices retained
  one Friends entry and did not duplicate the transcript. Private XML is excluded
  from this release.
- Live current BlueStacks check: a closed anonymous conversation was read and
  removed from engine state correctly, with Auto-reply OFF and no message sent.
- Live application matching command completed in approximately 4 seconds and
  produced one temporary conversation. Auto-reply remained OFF; no LLM send job was
  started in that test. This time includes Android XML reading and is not an SLA.
- A stale offline ADB connection after emulator startup was found during the live
  test. Targeted reconnect was added, tested and then successfully used for the
  closed-chat and matching checks. The shared ADB server is not reset.
- A real asynchronous call to local Ollama returned a 72-character response using
  synthetic test text. No customer conversation was used for that check.
- Dependency check passes. CLI reports 0.1.11. The paw-icon Windows launcher was
  compiled with file/product version 0.1.11.0.

## Remaining live limits

Fresh friendship request/acceptance observation through Computer Use is awaiting
owner approval for the current person. No new friend request or chat message was
sent in this validation pass. Historical acceptance XML and synthetic lifecycle
transitions passed, but they do not replace a fresh accepted request test.
Reply/delete menus and the Telegram handoff were covered by local tests, not a
complete live cross-account interaction in this pass.

The tests do not establish zero bugs or unattended production readiness. AnonChat
and Vidogram can change Android layouts. ADB exposes visible history and titles,
not stable server account/message IDs. Same-name contacts with indistinguishable
visible histories, unobserved anonymous transitions, and inaccessible/scrolled
messages cannot be resolved with API-level certainty. Non-overlapping known
history pauses replies instead of silently assigning it to the current person.

Telegram linking requires the one-use code shared by the owner; it is not inferred
from a matching name. Codes and chat memory last only for the current Rad.ai run.
ADB text entry supports printable ASCII. Actual latency includes XML dumps, model
generation and Android transitions. GUI and application matching were tested, but
a prolonged unattended live messaging soak test has not been completed.
