"""Build local CV references from Computer Use screenshots, without desktop input."""
import sys
from pathlib import Path
import json
import cv2
import numpy as np

root = Path(__file__).resolve().parent.parent / "outputs" / "chat_assistant_v0.2.0"
sys.path.insert(0, str(root))
from assistant.config import load, save
from assistant.desktop import Desktop, crop
from assistant.vision import dominant_color
from assistant.model import Ollama
import pytesseract

source = Path(__file__).resolve().parent / "calibration"
def read(name):
    return cv2.imdecode(np.fromfile(source / name, dtype=np.uint8), cv2.IMREAD_COLOR)
home, chat = read("anon-home.png"), read("anon-chat.png")
cfg = load()
p = cfg["profiles"]["anonchat"]
p.update(window_title="BlueStacks App Player 3", process_name="HD-Player.exe",
         size=[chat.shape[1], chat.shape[0]], read_mode="bubbles")
p["regions"] = {"chat": [7, 92, 386, 408], "identity": [14, 60, 115, 29]}
p["incoming_color"] = dominant_color(crop(chat, [15, 450, 57, 29]))
p["incoming_tolerance"] = 2
folder = root / "templates" / "anonchat"
folder.mkdir(parents=True, exist_ok=True)
for name, image, box in [("search", home, [42,421,315,53]),
                         ("empty_textbox", chat, [61,506,225,29]),
                         ("chat_anchor", chat, [23,511,21,23]),
                         ("next", chat, [14,648,372,38])]:
    cv2.imencode(".png", crop(image, box))[1].tofile(folder / (name + ".png"))
    p["templates"][name] = "templates/anonchat/" + name + ".png"
save(cfg)
driver = object.__new__(Desktop)
driver.profile = p
driver.scale = 1
pytesseract.pytesseract.tesseract_cmd = cfg["tesseract"]
incoming = driver.read_bubble(read("anon-ended.png"), "incoming")
print("Calibrated screenshot size:", p["size"])
print("Incoming bubble color:", p["incoming_color"])
print("OCR:", incoming)
if incoming:
    reply = Ollama(cfg)([{"role":"user", "content":incoming}])
    print("Draft:", reply)
