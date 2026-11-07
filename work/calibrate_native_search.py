from pathlib import Path
from PIL import Image
import json
root=Path(__file__).resolve().parent.parent/'outputs/chat_assistant_v0.2.0'
image=Image.open(root/'diagnostics/anonchat.png')
image.crop((339,527,729,595)).save(root/'templates/anonchat/search.png')
path=root/'profiles.json'
cfg=json.loads(path.read_text(encoding='utf-8-sig'))
cfg['profiles']['anonchat']['template_dpi']['search']=120
cfg['debug_capture']=False
path.write_text(json.dumps(cfg,indent=2),encoding='utf-8')
