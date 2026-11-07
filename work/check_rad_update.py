from pathlib import Path
import sys, json, time
import cv2, numpy as np
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/'outputs/rad_ai_v0.2.4'))
from assistant.autocalibration import AutoCalibrator, SCALE_HINTS
from assistant.model import Ollama
cfg=json.loads((root/'outputs/rad_ai_v0.2.4/profiles.json').read_text())
frame=cv2.imdecode(np.fromfile(root/'work/resume-backup/diagnostics/telegram.png',dtype=np.uint8),cv2.IMREAD_COLOR)
scanner=AutoCalibrator(cfg['profiles']['telegram'])
SCALE_HINTS.clear()
for label in ('Cold reference search','Cached reference search'):
    started=time.perf_counter()
    box=scanner.locate(frame,'chat_anchor',120,[0,460,660,460])
    print(label,round(time.perf_counter()-started,3),box,flush=True)
print('Local two-stage model smoke test:',Ollama(cfg)([
    {'role':'user','content':'Hi! [NEXT_INCOMING] How can you help me?'}]),flush=True)
