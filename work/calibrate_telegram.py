"""Create normal Telegram Desktop references from the authorized test chat."""
import sys
from pathlib import Path
import cv2
import numpy as np
import pytesseract

root = Path(__file__).resolve().parent.parent / "outputs" / "chat_assistant_v0.2.0"
sys.path.insert(0, str(root))
from assistant.config import load, save
from assistant.desktop import Desktop, crop
from assistant.vision import dominant_color
from assistant.model import Ollama

source = Path(__file__).resolve().parent / "calibration"
def read(name):
    return cv2.imdecode(np.fromfile(source/name, dtype=np.uint8), cv2.IMREAD_COLOR)
empty, draft, sent, menu = read("tg-empty.png"), read("tg-draft.png"), read("tg-sent.png"), read("tg-menu.png")
cfg = load()
p = cfg["profiles"]["telegram"]
p.update(window_title="", process_name="Telegram.exe", size=[sent.shape[1], sent.shape[0]],
         read_mode="bubbles", timestamp_inside=True, text_source="clipboard")
p["regions"] = {"chat": [214, 63, 306, 632], "identity": [220, 25, 48, 17]}
p["incoming_color"] = dominant_color(crop(sent, [225,666,175,22]))
p["outgoing_color"] = dominant_color(crop(sent, [269,620,230,31]))
p["incoming_tolerance"] = p["outgoing_tolerance"] = 8
folder = root/"templates"/"telegram"
folder.mkdir(parents=True,exist_ok=True)
for name, image, box in [("empty_textbox",empty,[246,705,126,20]),
                         ("chat_anchor",empty,[216,704,23,23]),
                         ("copy_text",menu,[318,565,90,24]),
                         ("send",draft,[492,697,33,35])]:
    cv2.imencode(".png",crop(image,box))[1].tofile(folder/(name+".png"))
    p["templates"][name] = "templates/telegram/"+name+".png"
save(cfg)
driver = object.__new__(Desktop)
driver.profile = p
driver.scale = 1
pytesseract.pytesseract.tesseract_cmd=cfg["tesseract"]
incoming=driver.read_bubble(sent,"incoming")
outgoing=driver.read_bubble(sent,"outgoing")
print("Screenshot size:",p["size"])
print("Incoming OCR:",incoming)
print("Outgoing OCR:",outgoing)
if incoming:
    print("Draft:",Ollama(cfg)([{"role":"user","content":incoming}]))
