from pathlib import Path
from PIL import Image
import json
root=Path(__file__).resolve().parent.parent
image=Image.open(root/'work/calibration/anon-pending-draft.png')
image.crop((579,664,607,693)).save(root/'outputs/chat_assistant_v0.2.0/templates/anonchat/send.png')
path=root/'outputs/chat_assistant_v0.2.0/profiles.json'
cfg=json.loads(path.read_text(encoding='utf-8-sig'))
p=cfg['profiles']['anonchat']
p['templates']['send']='templates/anonchat/send.png'
p['template_dpi']['send']=96
p['send_method']='button'
p['draft_from_anchor']={'x':64,'width':270,'top':-20,'height':40}
path.write_text(json.dumps(cfg,indent=2),encoding='utf-8')
