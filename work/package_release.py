from pathlib import Path
import zipfile
import json

workspace=Path(__file__).resolve().parent.parent
root=workspace/'outputs/chat_assistant_v0.2.0'
archive=workspace/'outputs/chat_assistant_v0.2.0.zip'
cfg=json.loads((root/'profiles.json').read_text(encoding='utf-8'))
assert cfg.get('debug_capture') is False
assert (root/'VERSION').read_text().strip()=='0.2.0'
allowed_roots={'assistant','templates','tests'}
allowed_files={'main.py','profiles.json','README.md','VALIDATION.md','RELEASE_NOTES.md',
               'requirements.txt','VERSION','Start.cmd','DesktopAssistant.exe'}
included=[]
with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as bundle:
    for path in sorted(root.rglob('*')):
        if not path.is_file() or '__pycache__' in path.parts:
            continue
        relative=path.relative_to(root)
        if relative.parts[0] not in allowed_roots and str(relative) not in allowed_files:
            continue
        bundle.write(path,Path(root.name)/relative)
        included.append(str(relative))
with zipfile.ZipFile(archive) as bundle:
    assert bundle.testzip() is None
print('Release archive:', archive)
print('Files:',len(included),'Bytes:',archive.stat().st_size)
