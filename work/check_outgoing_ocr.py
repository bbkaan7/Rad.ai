from pathlib import Path
import sys
import cv2
import numpy as np
import pytesseract
root=Path(__file__).resolve().parent.parent/'outputs/chat_assistant_v0.2.0'
sys.path.insert(0,str(root))
from assistant.desktop import Desktop, crop
from assistant.config import load
from assistant.vision import bubble_rectangles
cfg=load()
driver=object.__new__(Desktop)
driver.profile=cfg['profiles']['anonchat']
driver.scale=1
driver.dpi=96
driver.content_offset_x=226
pytesseract.pytesseract.tesseract_cmd=cfg['tesseract']
frame=cv2.imdecode(np.fromfile(Path(__file__).parent/'calibration/anon-sent-final.png',dtype=np.uint8),cv2.IMREAD_COLOR)
region=[233,92,386,572]  # Observed message pane in the saved logical-pixel fixture.
pane=crop(frame,region)
boxes=bubble_rectangles(pane,driver.profile['outgoing_color'],'right',8)
print('Region:',region,'Boxes:',boxes)
for i,box in enumerate(boxes):
    sample=crop(pane,box)
    cv2.imencode('.png',sample)[1].tofile(Path(__file__).parent/f'outgoing-{i}.png')
    print(i,repr(driver.ocr(sample)))
