# Rad.ai Bridge v0.1.15

Install/update `rad-bridge.apk` from Rad.ai Settings with both monitors stopped.
Enable Accessibility and Notification access manually in Android, then connect.
Updates preserve the pairing credential and normally preserve permissions.

The helper reads AnonChat and Telegram/Vidogram accessibility trees. Background
notifications are previews until history is verified. Android still has one
foreground window; muted/hidden notification text may require opening the chat.

The authenticated localhost service supports snapshots/events, opening a captured
notification, and compare-before-write edits to the single visible message editor.
It never presses Send itself. Password fields and other packages are excluded.
The desktop validates recipient/history before editing and before sending.

Sources: `src/ai/rad/bridge`. Build: `work/build_accessibility.py`, which downloads
official checksum-verified portable tools and signs the APK with the private local
development key in `runtime/`. Keep that key for compatible updates; the release
archive excludes it. This is a local development build.

To remove, stop monitoring, disable both Android permissions and uninstall Rad.ai
Bridge through Android settings. No platform session is stored by the helper.
