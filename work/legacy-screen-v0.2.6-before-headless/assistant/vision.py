"""Pure image operations for calibrated chat bubbles; no desktop input."""

import re

import cv2
import numpy as np


def bubble_rectangles(frame, background_bgr, side="left", tolerance=12):
    """Find solid message backgrounds, filtering by alignment in the chat pane."""
    color = np.asarray(background_bgr, dtype=np.int16)
    mask = np.all(np.abs(frame.astype(np.int16) - color) <= tolerance, axis=2).astype(np.uint8) * 255
    count, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    height, width = frame.shape[:2]
    boxes = []
    for x, y, w, h, area in stats[1:]:
        if w < 28 or h < 18 or area < w*h*0.20 or h > height*0.7:
            continue
        if side == "left" and x > width*0.20:
            continue
        if side == "right" and x+w < width*0.80:
            continue
        # Reject a pane background mistakenly selected as a bubble color.
        if w > width*0.98 or area > width*height*0.40:
            continue
        boxes.append((int(x), int(y), int(w), int(h)))
    return sorted(boxes, key=lambda box: (box[1], box[0]))


def strip_timestamp(text):
    text = " ".join(text.split())
    return re.sub(r"\s+\d{1,2}:\d{2}(?:\s*[APap][Mm])?(?:\s*[✓✔v]+)?$", "", text).strip()


def dominant_color(frame):
    colors, counts = np.unique(frame.reshape(-1, 3), axis=0, return_counts=True)
    return colors[counts.argmax()].tolist()


def ocr_image(frame):
    """Remove bright outer corners of dark rounded bubbles before OCR."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    background = float(np.median(gray))
    if background < 127:
        body = (gray < max(127, background + 40)).astype(np.uint8)
        contours, _ = cv2.findContours(body, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if contours:
            largest = max(contours, key=cv2.contourArea)
            if cv2.contourArea(largest) > gray.size * 0.2:
                silhouette = np.zeros_like(gray)
                # Filling the external contour preserves light glyphs inside it.
                cv2.drawContours(silhouette, [largest], -1, 255, cv2.FILLED)
                inner = cv2.erode(silhouette, np.ones((5, 5), np.uint8),
                                  borderType=cv2.BORDER_CONSTANT, borderValue=0)
                gray[inner == 0] = round(background)
        gray = cv2.bitwise_not(gray)
    gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
    return cv2.copyMakeBorder(gray, 12, 12, 12, 12, cv2.BORDER_CONSTANT, value=255)
