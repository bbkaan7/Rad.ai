from pathlib import Path
import zipfile
root=Path(__file__).resolve().parents[1]/'outputs/rad_ai_v0.2.6'
readme=(root/'README.md').read_text()
intro='''## Automatic new-match opening

On Anonchat, a new match following Search/Next or an observed home/ended screen
receives the literal `hii :3` automatically. This fixed text never goes through
Ollama. The greeting starts after the active chat is recognized and target checks
pass. Polling for a new active chat runs every 500 ms between operations; actual
latency also includes screen recognition and UI response, so it is not a real-time
latency guarantee.

After verified greeting submission, Rad.ai reads the visible labelled bio/profile
area and automatically sends a short conversation opener. This part uses the local
LLM. Missing or unreadable bio text results in a generic friendly question instead
of invented interests. New incoming messages during opener generation are included
before sending. The Draft greeting button and its manual-binding requirement are gone.

These two opening messages are automatic even when the separate auto-reply checkbox
is off. That checkbox controls subsequent replies. Pause/F10 stops pending actions.
The opening is attempted once per detected matching transition, including failed or
uncertain attempts. Uncertain sends require inspection rather than an automatic retry.
Selecting an already active conversation at startup does not itself count as a new
match; this prevents a repeated greeting when reopening the application. Telegram
does not receive automatic stranger greetings. Keep the intended Anonchat window
in the foreground and run only one Rad.ai instance.

'''
readme=readme.replace('## Incoming groups and two-stage replies',intro+'## Incoming groups and two-stage replies')
(root/'README.md').write_text(readme)
(root/'RELEASE_NOTES.md').write_text('''# Rad.ai v0.2.6

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
''')
(root/'VALIDATION.md').write_text('''# Rad.ai v0.2.6 validation

82 offline tests pass with desktop input mocked. Six new checks cover one-time
match claims, excluding existing/Telegram conversations, fixed greeting before
bio/Ollama, no model call after an uncertain greeting, labelled bio extraction,
and recipient-change rejection. The first outgoing text is exactly hii :3.

The inherited suite covers burst refresh, two-stage replies, per-part history,
visual matching, OCR, pending-send recovery and pause/focus guards.

Live fixed-greeting and bio-opener sending have not been tested. Bio OCR is limited
to labelled text visible above message bubbles; unavailable text uses a generic
opener. Matching identities are visual headers rather than platform account IDs.
Polling is 500 ms while waiting, plus actual capture/matching/UI time. There is no
measured end-to-end greeting latency guarantee. Unknown layouts, changes during
typing or an uncertain send still stop for inspection.

Physical mixed-DPI multi-monitor operation, sustained unattended operation and
live multipart sending remain unverified. One foreground chat and one app instance.
''')
with zipfile.ZipFile(root.parent/'rad_ai_v0.2.6.zip','w',zipfile.ZIP_DEFLATED) as bundle:
    for path in sorted(root.rglob('*')):
        if path.is_file() and not any(v in path.parts for v in ('__pycache__','diagnostics')) and path.suffix not in ('.pyc','.log','.tmp'):
            bundle.write(path,Path(root.name)/path.relative_to(root))
with zipfile.ZipFile(root.parent/'rad_ai_v0.2.6.zip') as bundle:
    assert bundle.testzip() is None
    print('Archive verified:',len(bundle.namelist()),'files')
