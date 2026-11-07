import sys
from pathlib import Path
import cv2
import numpy as np
import pytesseract
root=Path(__file__).resolve().parent.parent/"outputs"/"chat_assistant_v0.2.0"
sys.path.insert(0,str(root))
from assistant.config import load
from assistant.vision import bubble_rectangles
from assistant.desktop import crop
cfg=load()
p=cfg["profiles"]["telegram"]
pytesseract.pytesseract.tesseract_cmd=cfg["tesseract"]
frame=cv2.imdecode(np.fromfile(Path(__file__).parent/"calibration"/"tg-sent.png",dtype=np.uint8),cv2.IMREAD_COLOR)
pane=crop(frame,p["regions"]["chat"])
for direction,side in [("incoming","left"),("outgoing","right")]:
    boxes=bubble_rectangles(pane,p[direction+"_color"],side,8)
    print(direction,boxes[-1])
    bubble=crop(pane,boxes[-1])
    gray=cv2.cvtColor(bubble,cv2.COLOR_BGR2GRAY)
    gray=255-gray
    gray=cv2.resize(gray,None,fx=4,fy=4,interpolation=cv2.INTER_CUBIC)
    for method in ("gray","otsu","fixed"):
        image=gray if method=="gray" else cv2.threshold(gray,0 if method=="otsu" else 150,255,cv2.THRESH_BINARY+(cv2.THRESH_OTSU if method=="otsu" else 0))[1]
        image=cv2.copyMakeBorder(image,20,20,20,20,cv2.BORDER_CONSTANT,value=255)
        for mode in (6,11):
            print(method,mode,repr(pytesseract.image_to_string(image,config=f"--psm {mode}",lang="eng")))
