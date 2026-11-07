"""Build an allowlisted release without private runtime data or old executables."""
from pathlib import Path
import hashlib
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs'/'rad_ai_v0.1.11'
OUT.mkdir(parents=True,exist_ok=True)
files=['main.py','ayarlar.py','requirements.txt','settings.json','README.md',
       'VALIDATION.md','Start.cmd','Rad.ai.exe','.gitignore']
files += [str(p.relative_to(ROOT)) for folder in ('rad','tests')
          for p in (ROOT/folder).glob('*.py')]
files += [str(p.relative_to(ROOT)) for p in (ROOT/'assets').iterdir()
          if p.is_file() and p.suffix in {'.png','.ico','.json','.md'}]
files += ['work/HeadlessLauncher.cs','work/check_ui_0210.py']
for name in files:
    target=OUT/name
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(ROOT/name,target)
(OUT/'VERSION').write_text('0.1.11\n',encoding='utf-8')
files.append('VERSION')
manifest=''.join(hashlib.sha256((OUT/name).read_bytes()).hexdigest()+'  '+Path(name).as_posix()+'\n'
                 for name in sorted(files))
(OUT/'SHA256SUMS.txt').write_text(manifest,encoding='utf-8')
archive_path=OUT.parent/(OUT.name+'.zip')
with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED) as archive:
    for name in sorted(files+['SHA256SUMS.txt']):
        archive.write(OUT/name,Path(OUT.name)/name)
with zipfile.ZipFile(archive_path) as archive:
    assert archive.testzip() is None
    assert not any('runtime/' in n or '__pycache__' in n or '.session' in n for n in archive.namelist())
print('Release:',OUT)
print('Verified ZIP:',archive_path,'files:',len(files)+1)
