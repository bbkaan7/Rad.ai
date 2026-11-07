from pathlib import Path
import cv2
import numpy as np
import pytesseract
pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
frame=cv2.imdecode(np.fromfile(Path(__file__).parent/'ocr-bubble-1.png',dtype=np.uint8),cv2.IMREAD_GRAYSCALE)
for scale in (2,3,4):
    gray=cv2.resize(frame,None,fx=scale,fy=scale,interpolation=cv2.INTER_CUBIC)
    for method in ('gray','otsu','fixed'):
        processed=gray if method=='gray' else cv2.threshold(gray,0 if method=='otsu' else 180,255,cv2.THRESH_BINARY+(cv2.THRESH_OTSU if method=='otsu' else 0))[1]
        processed=cv2.copyMakeBorder(processed,12,12,12,12,cv2.BORDER_CONSTANT,value=255)
        for mode in (6,7,11):
            print(scale,method,mode,repr(pytesseract.image_to_string(processed,lang='eng',config=f'--psm {mode}')))
