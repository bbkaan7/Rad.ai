from pathlib import Path
import sys
import cv2
import numpy as np
import pytesseract

root = Path(__file__).resolve().parent.parent / 'outputs' / 'chat_assistant_v0.2.0'
sys.path.insert(0, str(root))
from assistant.desktop import Desktop, crop
from assistant.config import load
from assistant.vision import bubble_rectangles

config = load()
driver = object.__new__(Desktop)
driver.profile = config['profiles']['anonchat']
driver.scale = 1
driver.content_offset_x = 226
pytesseract.pytesseract.tesseract_cmd = config['tesseract']
frame = cv2.imdecode(np.fromfile(Path(__file__).parent / 'calibration' / 'anon-resume-ended.png', dtype=np.uint8), cv2.IMREAD_COLOR)
pane = crop(frame, driver.region('chat'))
boxes = bubble_rectangles(pane, [255,255,255], tolerance=2)
print('Image:', frame.shape, 'Bubble rectangles:', boxes)
for index, box in enumerate(boxes):
    sample = crop(pane, box)
    cv2.imencode('.png', sample)[1].tofile(Path(__file__).parent / f'ocr-bubble-{index}.png')
    print(index, repr(driver.ocr(sample)))
