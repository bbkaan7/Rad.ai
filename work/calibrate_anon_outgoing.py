from pathlib import Path
from collections import Counter
from PIL import Image
import json
root=Path(__file__).resolve().parent.parent
image=Image.open(root/'work/calibration/anon-friend-chat.png').convert('RGB')
color=Counter(image.crop((566,451,611,479)).getdata()).most_common(1)[0][0]
path=root/'outputs/chat_assistant_v0.2.0/profiles.json'
cfg=json.loads(path.read_text(encoding='utf-8-sig'))
cfg['profiles']['anonchat']['outgoing_color']=list(reversed(color))
cfg['profiles']['anonchat']['outgoing_tolerance']=8
path.write_text(json.dumps(cfg,indent=2),encoding='utf-8')
print('Outgoing bubble BGR:',list(reversed(color)))
