from pathlib import Path
import sys
import cv2
import numpy as np
import pytesseract
root=Path(__file__).resolve().parent.parent/'outputs/chat_assistant_v0.2.0'
sys.path.insert(0,str(root))
from assistant.desktop import Desktop, crop
from assistant.vision import bubble_rectangles, ocr_image
from assistant.config import load
cfg=load()
driver=object.__new__(Desktop)
driver.profile=cfg['profiles']['anonchat']
driver.scale=1.25
driver.dpi=120
driver.content_offset_x=282
pytesseract.pytesseract.tesseract_cmd=cfg['tesseract']
frame=cv2.imdecode(np.fromfile(root/'diagnostics/anonchat.png',dtype=np.uint8),cv2.IMREAD_COLOR)
print('Native frame:',frame.shape)
print('Input anchor:',driver.find(frame,'chat_anchor'))
text=driver.read_bubble(frame,'outgoing')
pane=crop(frame,driver.message_region(frame))
box=bubble_rectangles(pane,driver.profile['outgoing_color'],'right',8)[-1]
sample=crop(pane,box)
cv2.imencode('.png',ocr_image(sample))[1].tofile(Path(__file__).parent/'native-outgoing-prepared.png')
print('Outgoing OCR:',repr(text))
assert text=='Thanks for helping with the test.', 'Exact verification still needs manual reconciliation'
print('Exact outgoing verification passed on native capture.')
