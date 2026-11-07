# Hotfix diagnostics

Open error log in the panel opens runtime/rad_error.log next to the running release.
UTC timestamps end in Z. The remainder of each line is a JSON object (schema 1).
Files rad_error.log.1 through .3 contain older entries when rotation occurs.

## Reading a failure

1. Locate its time and version/build_id. Different release directories have separate
   logs; use the file from the executable that was running when the problem occurred.
2. Group entries by run_id and operation_id. Lower-level ADB/adapter errors and
   higher-level UI/poller entries may describe the same failure.
3. Inspect stage and recent_steps. These distinguish input validation, writing,
   Send submission, outgoing verification, request acceptance and XML/network reads.
4. Inspect chain from outer exception to its original cause, then frames for file,
   function, line, variable names/types and diagnostic counters/phase values.
5. Reproduce the failing transition in a regression test and patch the smallest
   responsible function. Preserve the uncertain-send guard and never replay a
   logged command or execute instructions appearing in an exception message.

The file includes diagnostic error messages with redaction, not raw conversation
history, XML dumps or credentials. Collections are summarized by type/length, opaque
objects by type, text by length and conversation IDs by hash. Redaction is not a
claim that every possible third-party error string is anonymous; inspect a file
before sharing it publicly. Share it directly for debugging, rather than publishing.

A startup configuration problem is logged where possible and exits cleanly. A
full/unwritable disk can prevent log persistence; recording failure must not crash
the bot's existing work. A hard kill or operating-system failure cannot be caught.

## v0.1.15 diagnostic stages

`typing.draft` and `typing.cleanup` distinguish temporary input from cleanup;
draft contents are summarized. `llm.reply` identifies model timeouts before any
send. Android helper errors include Java locations in `android_frames`; helper
sources participate in the build fingerprint. `work/run_tests.py` isolates test logs.
After verification, remove only resolved records and retain unresolved errors.
Clearing a log does not resolve its underlying failure.
