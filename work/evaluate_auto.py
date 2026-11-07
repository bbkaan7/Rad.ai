from pathlib import Path
import sys,json,time
import cv2,numpy as np,pytesseract
workspace=Path(__file__).resolve().parent.parent
root=workspace/'outputs/rad_ai_v0.2.4'
sys.path.insert(0,str(root))
from assistant.autocalibration import AutoCalibrator
cfg=json.loads((root/'profiles.json').read_text())
pytesseract.pytesseract.tesseract_cmd=cfg['tesseract']
cases=[('anonchat','anonchat-home-native.png'),('anonchat','anonchat-final-native.png'),('telegram','telegram.png')]
for platform,filename in cases:
    image=cv2.imdecode(np.fromfile(workspace/'work/resume-backup/diagnostics'/filename,dtype=np.uint8),cv2.IMREAD_COLOR)
    started=time.monotonic()
    try:
        profile=AutoCalibrator(cfg['profiles'][platform]).analyze(image,120)
        print(filename,round(time.monotonic()-started,2),{k:profile.get(k) for k in ('auto_state','auto_viewport','regions','incoming_color','outgoing_color')},flush=True)
    except Exception as error:
        print(filename,type(error).__name__,str(error),flush=True)
