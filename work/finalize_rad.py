from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1] / 'outputs' / 'rad_ai_v0.2.4'
readme = (root/'README.md').read_text(encoding='utf-8')
readme = readme.replace('Desktop Assistant — v0.2.0 supervised alpha', 'Rad.ai — v0.2.4 supervised alpha')
readme = readme.replace('DesktopAssistant.exe', 'Rad.ai.exe')
readme = readme.replace('use calibrated visual references', 'use bundled visual references and automatic layout detection')
readme = readme.replace('requires message-pane, incoming-bubble and active-input calibration', 'requires a recognizable active chat and incoming message')
start = readme.index('## Calibration and monitors')
end = readme.index('## Stop and recovery')
readme = readme[:start] + '''## Automatic calibration and monitors

There is no manual region-selection step. Open the supported application, select
the platform, then use **Bind current chat**. Screen actions discover the layout
automatically. **Auto-calibrate** performs an optional read-only rescan and clears
the panel's bound conversation and draft. It does not send a message.

The scanner discovers the Anonchat light application surface, excludes the
BlueStacks advertisement dock, finds input controls at multiple scales, reads a
bounded recipient header and learns bubble colors from visible content. Telegram's
chat-list divider is detected from its input row. Window movement uses current
window bounds; a size or DPI change causes a fresh scan. If the window moves during
an operation, the action stops. Rebind after resizing or changing recipients.

Bundled visual references in `templates/` support the tested English Anonchat
light interface and Telegram Desktop layout. Search/Next labels have an OCR
fallback. Unknown or ambiguous screens stop instead of guessing a click. A new
theme, application redesign, very small window or overlay can require a future
reference update. Automatic calibration does not guarantee every resolution or
theme. Physical mixed-DPI multi-monitor operation remains unverified.

Use the optional window filter only when multiple target windows are open.
Settings are local in `profiles.json`; `vision_profiles.json` supplies clean
defaults. No customer screenshots or message history are bundled in the release.
Header images are change detectors, not verified account IDs; identical cropped
headers may be indistinguishable. Use one foreground conversation at a time.

''' + readme[end:]
(root/'README.md').write_text(readme, encoding='utf-8')
(root/'RELEASE_NOTES.md').write_text('''# Rad.ai v0.2.4

- Renamed the application to Rad.ai and added the supplied paw logo to the panel
  and window icon. Version labels use 0.2.4 without development suffixes.
- Replaced manual calibration controls with automatic layout discovery before
  screen actions and an optional Auto-calibrate rescan.
- Added multi-scale reference matching, Anonchat surface/ad-dock separation,
  Telegram divider discovery, header extraction and automatic bubble-color learning.
- Added exact Search/Next label fallback and rejection of ambiguous detections.
- Preserved reviewed replies, rewriting, pause, recipient/message checks and
  pending-send recovery. Experimental auto-send remains off by default.
- Application UI, messages and documentation remain English.

Open Rad.ai.exe or Start.cmd. The existing Python environment, Tesseract, Ollama
and signed-in target applications are required; this is not a standalone installer.
See VALIDATION.md for tested behavior and remaining limitations.
''', encoding='utf-8')

(root/'VALIDATION.md').write_text('''# Validation — Rad.ai 0.2.4

Date: 2026-10-02

## Automated regression checks

68 tests passed, no skips, in the existing Windows Python environment. Desktop
input and clipboard calls in unit tests are mocked. Coverage includes conversation
isolation, stale/duplicate reply rejection, manual reconciliation, pause, rewrite,
greetings, guarded sending, exact-draft recovery, clipboard freshness, moving-window
rejection, negative screen coordinates, DPI/dock behavior and OCR preprocessing.

New automatic-calibration tests cover surface discovery, advertisement exclusion,
multi-scale reference matching, ambiguous-reference rejection, divider detection,
bounded header extraction, empty panes, bubble-color learning, clearing stale chat
regions, unique OCR labels, label search bounds and rejecting ambiguous fallbacks.

## Local image replay

Three previous native captures (Anonchat home, Anonchat friend chat, Telegram chat)
were recognized from profiles with no saved regions or bubble colors. All nine
resized variants at 0.8x/96 DPI, 1.2x/144 DPI and 1.5x/180 DPI were recognized.
Both Anonchat captures also passed after removing the advertisement dock. The
current 455x782 Anonchat home capture passed after the fine-scale and label fix.
These are image-replay checks, not physical multi-monitor tests.

## Live checks for this revision

- Rad.ai.exe launched the panel; the supplied paw appears in the header and title
  icon. Restart loaded the latest code and retained the version label 0.2.4.
- Auto-calibrate recognized the current Anonchat home screen without manual
  region selection and reported `Automatic calibration complete: home`.
- Telegram with no selected chat stopped with an instruction to open a private
  chat. After opening the designated test chat, automatic calibration reported
  `Automatic calibration complete: chat` without manual region selection.
- Experimental auto-send remained unchecked. No new messages were sent in this
  revision's calibration tests.

## Evidence inherited from v0.2.0

The previous release exercised local generation/rewrite, Telegram Copy Text,
approved sends on Telegram and Anonchat, Anonchat matching and watch-preview.
The user confirmed physical F10 pauses input. Those checks are historical evidence;
the full send flow has not been repeated after this calibration rewrite.

## Limits

- This is a supervised single-chat alpha, not an unattended service.
- Physical mixed-DPI multi-monitor use and sustained auto-send remain unverified.
- Theme changes, unsupported layouts, overlays or tiny text can stop recognition.
- Headers are visual change detectors, not platform account IDs. Rebind after
  changing recipients or resizing; do not rely on visually identical names.
- OCR and the small local model can make mistakes. Review incoming text and drafts.
- Seeing an outgoing bubble proves visible submission, not server delivery.
- Live greeting submission and the new pending-send recovery UI remain unverified.
- Target apps must be open and signed in. No unattended login/account recovery,
  persistent customer memory or parallel-chat scheduler is included.

Diagnostic capture is disabled. Source screenshots stay in the local work area
and are excluded from the release archive.
''', encoding='utf-8')

archive = root.parent / 'rad_ai_v0.2.4.zip'
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as bundle:
    for path in sorted(root.rglob('*')):
        if not path.is_file() or any(part in {'__pycache__','diagnostics'} for part in path.parts):
            continue
        if path.suffix in {'.pyc','.log','.tmp'}:
            continue
        bundle.write(path, Path(root.name)/path.relative_to(root))
with zipfile.ZipFile(archive) as bundle:
    assert bundle.testzip() is None
    print(f'Archive verified: {len(bundle.namelist())} files, {archive.stat().st_size} bytes')
