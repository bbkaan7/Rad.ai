"""Automatic visual layout discovery; no input, screen capture or network access."""

from copy import deepcopy
from pathlib import Path
import re
from functools import lru_cache

import cv2
import numpy as np
import pytesseract

from .config import ROOT
from .vision import bubble_rectangles


class CalibrationError(ValueError):
    pass


def clipped(region, shape):
    x, y, w, h = map(int, region)
    x, y = max(0, x), max(0, y)
    w, h = min(w, shape[1] - x), min(h, shape[0] - y)
    if w < 4 or h < 4:
        raise CalibrationError("The detected layout is too small. Enlarge the application window.")
    return [x, y, w, h]


@lru_cache(maxsize=64)
def reference_image(path, modified):
    return cv2.imdecode(np.fromfile(Path(path), dtype=np.uint8), cv2.IMREAD_GRAYSCALE)


SCALE_HINTS = {}


def reference_match(frame, path, source_dpi, dpi, area=None, threshold=0.88, factors=None):
    """Search supported reference scales and reject distinct competing matches."""
    path = Path(path)
    template = reference_image(str(path), path.stat().st_mtime_ns)
    if template is None or template.std() < 2:
        raise CalibrationError("A bundled visual reference is missing or invalid.")
    area = clipped(area or [0, 0, frame.shape[1], frame.shape[0]], frame.shape)
    ax, ay, aw, ah = area
    gray = cv2.cvtColor(frame[ay:ay+ah, ax:ax+aw], cv2.COLOR_BGR2GRAY)
    candidates = []
    base = dpi / source_dpi
    for factor in (factors if factors is not None else sorted(np.arange(0.65,1.551,0.025),key=lambda value:abs(value-1))):
        scale = base * factor
        w, h = round(template.shape[1]*scale), round(template.shape[0]*scale)
        if min(w, h) < 8 or w > aw or h > ah:
            continue
        resized = cv2.resize(template, (w, h), interpolation=cv2.INTER_CUBIC)
        scores = cv2.matchTemplate(gray, resized, cv2.TM_CCOEFF_NORMED)
        for _ in range(2):
            _, score, _, point = cv2.minMaxLoc(scores)
            if not np.isfinite(score) or score < threshold:
                break
            x, y = point
            candidates.append((score, ax+x, ay+y, w, h))
            scores[max(0,y-h//2):y+h//2+1, max(0,x-w//2):x+w//2+1] = -1
    if not candidates:
        raise CalibrationError("Control not recognized. Keep the supported application visible; no click was made.")
    candidates.sort(reverse=True)
    best = candidates[0]
    _, bx, by, bw, bh = best
    for score, x, y, w, h in candidates[1:]:
        if abs(x+w/2-bx-bw/2) > max(w,bw)*0.6 or abs(y+h/2-by-bh/2) > max(h,bh)*0.6:
            raise CalibrationError("More than one control matches. No click was made.")
    return [bx, by, bw, bh]


def anon_viewport(frame):
    """Find the large light application surface, excluding the emulator ad dock."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    mask = ((hsv[:,:,1] < 32) & (hsv[:,:,2] > 230)).astype(np.uint8)
    _, _, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    height, width = frame.shape[:2]
    choices = []
    for x,y,w,h,area in stats[1:]:
        if h > height*0.60 and w > width*0.25 and area > width*height*0.14:
            choices.append((int(area), [int(x),int(y),int(w),int(h)]))
    if not choices:
        raise CalibrationError("Anonchat's light application surface was not recognized. Open Anonchat and dismiss overlays.")
    choices.sort(reverse=True)
    if len(choices)>1 and choices[1][0] > choices[0][0]*0.75:
        raise CalibrationError("The application surface is ambiguous. Close the overlay and retry.")
    return choices[0][1]


def telegram_left(frame, anchor, dpi):
    """Locate the long chat-list divider next to the input attachment icon."""
    x = anchor[0] + anchor[2]//2
    scale = dpi/96
    lo, hi = max(1, x-round(90*scale)), max(2,x-round(8*scale))
    difference = np.max(np.abs(frame[:,1:].astype(np.int16)-frame[:,:-1].astype(np.int16)),axis=2)
    counts = np.mean(difference > 7, axis=0)
    selected = lo + int(np.argmax(counts[lo:hi]))
    return selected+1 if counts[selected] > 0.45 else 0


def header_region(frame, area, dpi, data_reader=None):
    """Read only the header strip; never derive identity from the conversation body."""
    x,y,w,h = clipped(area, frame.shape)
    image = frame[y:y+h,x:x+w]
    reader = data_reader or pytesseract.image_to_data
    data = reader(image, lang="eng", config="--psm 6", output_type=pytesseract.Output.DICT, timeout=10)
    lines = {}
    for i, text in enumerate(data["text"]):
        text = text.strip()
        if not text or float(data["conf"][i]) < 30:
            continue
        if int(data["height"][i]) > 24*dpi/96:
            continue  # Avatars occasionally produce a tall false OCR token.
        key = (data["block_num"][i],data["par_num"][i],data["line_num"][i])
        lines.setdefault(key,[]).append((text,int(data["left"][i]),int(data["top"][i]),int(data["width"][i]),int(data["height"][i])))
    possible = []
    for words in lines.values():
        text = " ".join(word[0] for word in words)
        if not re.search(r"[A-Za-z]",text) or re.search(r"^(online|last seen|typing|connecting|searching)\b",text,re.I):
            continue
        left=min(a[1] for a in words); top=min(a[2] for a in words)
        right=max(a[1]+a[3] for a in words); bottom=max(a[2]+a[4] for a in words)
        possible.append((top,[x+left-2,y+top-2,right-left+4,bottom-top+4]))
    if not possible:
        raise CalibrationError("The chat header is unreadable. Keep the recipient name visible and retry.")
    return clipped(min(possible,key=lambda item:item[0])[1],frame.shape)


def infer_colors(pane):
    """Learn aligned solid bubble backgrounds from visible image content."""
    pixels = pane[::2,::2].reshape(-1,3)
    colors,counts = np.unique(pixels,axis=0,return_counts=True)
    ranked = np.argsort(counts)[-24:][::-1]
    result = {}
    for direction,side in (("incoming","left"),("outgoing","right")):
        scored = []
        for index in ranked:
            if counts[index] < 20:
                continue
            color = colors[index].tolist()
            tolerance = 2 if min(color)>240 else 8
            boxes = bubble_rectangles(pane,color,side,tolerance)
            boxes = [b for b in boxes if b[2]>b[3] and b[3]<pane.shape[0]*0.25]
            if boxes:
                latest=max(boxes,key=lambda b:b[1])
                scored.append((latest[1]+latest[3],counts[index],color,tolerance))
        if scored:
            _,_,color,tolerance=max(scored,key=lambda a:(a[0],a[1]))
            result[direction+"_color"]=color
            result[direction+"_tolerance"]=tolerance
    return result


def labelled_control(frame, name, area=None):
    x,y,w,h=clipped(area or [0,0,frame.shape[1],frame.shape[0]],frame.shape)
    # Restrict matching to the control area, excluding recipient names in headers.
    start=y+round(h*.40)
    data=pytesseract.image_to_data(frame[start:y+h,x:x+w],lang="eng",config="--psm 11",
                                   output_type=pytesseract.Output.DICT,timeout=10)
    lines={}
    for i,word in enumerate(data['text']):
        if word.strip() and float(data['conf'][i])>=55:
            key=(data['block_num'][i],data['par_num'][i],data['line_num'][i])
            lines.setdefault(key,[]).append(i)
    matches=[]
    expected={"search":{"start searching","search for partner"},"next":{"new partner","next partner"}}[name]
    for indices in lines.values():
        label=" ".join(data['text'][i].lower().strip() for i in indices)
        if label not in expected:
            continue
        left=min(data['left'][i] for i in indices); top=min(data['top'][i] for i in indices)
        right=max(data['left'][i]+data['width'][i] for i in indices)
        bottom=max(data['top'][i]+data['height'][i] for i in indices)
        matches.append([x+left,start+top,right-left,bottom-top])
    if len(matches)!=1:
        raise CalibrationError("A unique labelled control was not recognized; no click was made.")
    return matches[0]


class AutoCalibrator:
    def __init__(self, profile):
        self.profile = profile

    def locate(self, frame, name, dpi, area=None):
        path = self.profile["templates"].get(name)
        if not path:
            raise CalibrationError(f"No supported visual reference for {name}.")
        try:
            source_dpi = self.profile.get("template_dpi",{}).get(name,96)
            key = (str(ROOT/path), source_dpi, dpi, frame.shape[:2])
            hint = SCALE_HINTS.get(key)
            if hint is not None:
                try:
                    return reference_match(frame, ROOT/path, source_dpi, dpi, area, factors=[hint])
                except CalibrationError as error:
                    if "More than one" in str(error):
                        raise
            box = reference_match(frame, ROOT/path, source_dpi, dpi, area)
            template = reference_image(str(ROOT/path), (ROOT/path).stat().st_mtime_ns)
            SCALE_HINTS[key] = box[2] / template.shape[1] / (dpi/source_dpi)
            if len(SCALE_HINTS) > 128:
                SCALE_HINTS.clear()
            return box
        except CalibrationError as error:
            # Text-labelled controls can change width independently of their font.
            if name not in {"search", "next"} or "More than one" in str(error):
                raise
            return labelled_control(frame,name,area)


    def analyze(self, frame, dpi):
        result=deepcopy(self.profile)
        height,width=frame.shape[:2]
        scale=dpi/96
        is_anon=result.get("process_name","").lower()=="hd-player.exe"
        viewport=anon_viewport(frame) if is_anon else [0,0,width,height]
        x,y,w,h=viewport
        input_area=[x,y+round(h*.45),w,round(h*.55)]
        try:
            anchor=self.locate(frame,"chat_anchor",dpi,input_area)
        except CalibrationError:
            if not is_anon:
                raise CalibrationError("Open a Telegram private chat with its input row visible.")
            state="unknown"
            for control in ("search","next"):
                try:
                    self.locate(frame,control,dpi,viewport)
                    state="home" if control=="search" else "ended"
                    break
                except CalibrationError:
                    continue
            if state=="unknown":
                raise CalibrationError("Waiting for a supported Anonchat screen. Dismiss dialogs or wait for loading to finish.")
            result.update(regions={},auto_state=state)
        else:
            if not is_anon:
                x=telegram_left(frame,anchor,dpi)
                y=round(24*scale); w=width-x; h=height-y
                viewport=[x,y,w,h]
            header_area=([x+round(w*.10),y+round(16*scale),round(w*.72),round(42*scale)]
                         if is_anon else [x+round(10*scale),round(27*scale),w-round(70*scale),round(45*scale)])
            identity=header_region(frame,header_area,dpi)
            top=identity[1]+identity[3]+round(23*scale)
            bottom=anchor[1]-round(6*scale)
            chat=clipped([x+round(6*scale),top,w-round(12*scale),bottom-top],frame.shape)
            result.update(regions={"identity":identity,"chat":chat},read_mode="bubbles",auto_state="chat")
            result["chat_bottom_from_anchor"]=round(anchor[3]/2+6*scale)
            result.update(infer_colors(frame[chat[1]:chat[1]+chat[3],chat[0]:chat[0]+chat[2]]))
            if is_anon:
                result["draft_from_anchor"]={"x":anchor[0]+anchor[2]+round(8*scale),
                    "width":max(20,x+w-anchor[0]-anchor[2]-round(60*scale)),
                    "top":-round(22*scale),"height":round(44*scale)}
        result.update(size=[width,height],reference_dpi=dpi,auto_viewport=viewport,auto_calibration=True)
        result.pop("left_dock_width",None)
        return result
