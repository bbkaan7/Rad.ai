"""Upgrade only known calibration references from the app's local diagnostic frame."""
import sys
from pathlib import Path
import cv2
root=Path(__file__).resolve().parent.parent/"outputs"/"chat_assistant_v0.2.0"
sys.path.insert(0,str(root))
from assistant.config import load,save
from assistant.desktop import crop
cfg=load()
p=cfg["profiles"]["telegram"]
frame=cv2.imread(str(root/"diagnostics"/"telegram.png"))
for name,box in [("chat_anchor",[270,880,29,29]),("empty_textbox",[308,881,157,25])]:
    cv2.imencode(".png",crop(frame,box))[1].tofile(root/p["templates"][name])
    p.setdefault("template_dpi",{})[name]=120
save(cfg)
print("Native-resolution input references saved.")
