"""English-only chat settings. Edit regions and reference images for your app."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# Physical pixels on the primary monitor. Include only the latest incoming message.
CHAT_REGION = {'left': 100, 'top': 200, 'width': 700, 'height': 350}
# None searches the entire primary monitor; use a region to restrict matching.
SEARCH_REGION = None
TEXTBOX_IMAGE = ROOT / 'templates' / 'textbox.png'
SEND_IMAGE = ROOT / 'templates' / 'send_btn.png'
MATCH_THRESHOLD = 0.88
# Use "button" or "enter".
SEND_METHOD = 'button'
OLLAMA_URL = 'http://localhost:11434/api/generate'
# Must match a locally installed Ollama model.
MODEL = 'llama3.2:1b'
# Connection and response timeouts in seconds.
API_TIMEOUT = (5, 90)
PROMPT = 'You are a chat bot. Always reply only in English, regardless of the language of the incoming message. Keep your reply short and natural. Return only the reply text. Incoming message: {message}'
# Full executable path, or None when Tesseract is available on PATH.
TESSERACT_PATH = 'C:\\Program Files\\Tesseract-OCR\\tesseract.exe'
OCR_LANGUAGE = 'eng'
OCR_TIMEOUT = 15
OCR_CONFIG = '--psm 6'
# Use "region" for one message, or "last_paragraph" as a layout-dependent heuristic.
MESSAGE_SELECTION = 'region'
TYPING_INTERVAL = 0.05
UI_DELAY = 0.3
MAX_REPLY_LENGTH = 1500
