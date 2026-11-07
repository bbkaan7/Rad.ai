# Rad.ai 0.2.9 validation

- 70 unit/regression tests pass, including scheduling, launch cooldown, retry,
  local-search navigation, ambiguity rejection, chat isolation and backgrounding.
- Live receive-only test: 43 seconds with both platforms connected; four launches
  spaced 12.5, 12.3 and 12.6 seconds apart. No outgoing messages were submitted.
- Local search opened the existing theurgist test chat and verified its header.
- Both Android processes remained running after the switching test.
- Device-lock tests reject a second controller and permit reconnection after release.
- UI labels use Telegram; Android package identifiers continue to target Vidogram.
- Light/Dark/Light UI integration checks pass: logo/icon load, theme colors,
  sparse paw patterns and message bubbles. PNG alpha and seven ICO sizes verified.
- The user manually checked the visuals and confirmed they look good. Automated
  Windows screenshot inspection was blocked by the control tool's window-owner error.
- pip check passes. The launcher is compiled with the paw ICO and version metadata.

## Limits

This short live test is not a long-duration reliability guarantee. Android layout
changes, duplicate display names, renames, missing/scrolled history, and anonymous
partners with indistinguishable headers cannot be resolved with API-level certainty.
Known Telegram chats rotate through local search; complete account discovery is not
claimed. Open saved AnonChat friends inside Android before operating on them.
Friend acceptance, reply and delete controls remain conditional on supported XML;
those actions were not live-tested in this turn. No claim of universal app control.
Telegram presence may remain online during active ADB monitoring or other sessions.
