from pathlib import Path
import shutil
import zipfile
import subprocess

root=Path(__file__).resolve().parents[1]
output=(root/'outputs/rad_ai_v0.2.6').resolve()
backup=(root/'work/legacy-screen-v0.2.6-before-headless').resolve()
# Validate both endpoints before moving the old release directory on Windows.
assert output.parent == (root/'outputs').resolve()
assert backup.parent == (root/'work').resolve()
if output.exists():
    if backup.exists():
        raise RuntimeError('Backup already exists; do not overwrite it.')
    shutil.move(str(output),str(backup))
old_zip=root/'outputs/rad_ai_v0.2.6.zip'
if old_zip.exists():
    zip_backup=root/'work/legacy-screen-v0.2.6-before-headless.zip'
    if zip_backup.exists():
        raise RuntimeError('Archive backup already exists.')
    shutil.move(str(old_zip),str(zip_backup))
output.mkdir(parents=True)
files=['main.py','ayarlar.py','requirements.txt','settings.json','README.md','Start.cmd','Rad.ai.exe']
for name in files:
    shutil.copy2(root/name,output/name)
for folder in ['rad','tests']:
    shutil.copytree(root/folder,output/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
(output/'VERSION').write_text('0.2.6\n')
lock=subprocess.check_output([str(root/'.venv/Scripts/python.exe'),'-m','pip','freeze'],text=True)
(output/'requirements.lock.txt').write_text(lock)
(output/'VALIDATION.md').write_text('''# API/ADB v0.2.6 validation

17 offline tests passed, using synthetic XML and mocked network/device sends.
Coverage: five-message context isolation, duplicate occurrences, XML bounds,
shell quoting, unsupported Unicode, burst updates during generation and sending,
manual takeover, global auto-off, uncertain send rejection, historical-event
suppression, typed-text verification and changed-recipient rejection.

The isolated environment passes pip check. All new modules compile and import.
A real async aiohttp call to local Ollama /api/generate returned a text reply.
The new Rad.ai v0.2.6 window appeared in the desktop window list. Visual inspection
was blocked by the desktop tool reporting that the window no longer belonged to
the same reported application identifier. No visual verification is claimed.

Live Telegram authentication and AnonChat XML selectors have not been configured.
No live account messages were sent. ADB match lifecycle, online presence and typing
indicators need account/device integration testing after local setup.

The active distribution contains no legacy screen/OCR adapters or dependencies.
Previous screen-based files are retained only in a local work-area backup.
''')
with zipfile.ZipFile(old_zip,'w',zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(output.rglob('*')):
        if path.is_file() and not any(part in {'runtime', '__pycache__', '.venv'} for part in path.relative_to(output).parts) and path.suffix not in {'.pyc', '.session'}:
            archive.write(path,Path(output.name)/path.relative_to(output))
with zipfile.ZipFile(old_zip) as archive:
    assert archive.testzip() is None
    print('Verified API/ADB release archive:',len(archive.namelist()),'files')
