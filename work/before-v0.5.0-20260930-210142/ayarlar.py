from pathlib import Path

KOK = Path(__file__).resolve().parent

# Birincil monitörde, mümkünse sadece son gelen mesajı kapsayan alan.
SOHBET_BOLGESI = {"left": 100, "top": 200, "width": 700, "height": 350}
# None: birincil monitörün tamamında ara. İstersen yukarıdaki gibi alan ver.
ARAMA_BOLGESI = None

TEXTBOX_RESIM = KOK / "templates" / "textbox.png"
GONDER_RESIM = KOK / "templates" / "send_btn.png"
ESLESME_ESIGI = 0.88
GONDERME_YONTEMI = "buton"  # "buton" veya "enter"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "llama3.2:1b"  # Ollama'da indirdiğin model adıyla değiştir.
API_TIMEOUT = (5, 90)  # Bağlanma ve yanıt bekleme süreleri (saniye).
PROMPT = "You are a chat bot. Always reply only in English, regardless of the language of the incoming message. Keep your reply short and natural. Return only the reply text. Incoming message: {mesaj}"

# Tesseract PATH'te değilse örn. r"C:\Program Files\Tesseract-OCR\tesseract.exe".
TESSERACT_YOLU = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
OCR_DILI = "eng"
OCR_TIMEOUT = 15
OCR_CONFIG = "--psm 6"
# "bolge": bölgenin tamamı tek mesaj; "son_paragraf": son boşlukla ayrılmış blok.
# Son paragraf yöntemi konuşmacıları ayırt etmez; çok satırlı mesajları bölebilir.
MESAJ_SECIMI = "bolge"

YAZMA_ARALIGI = 0.05
UI_BEKLEME = 0.3
AZAMI_CEVAP_UZUNLUGU = 1500
