import ast
import io
from pathlib import Path
import re
import tokenize

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / 'outputs' / 'sohbet_alpha'
names = dict(zip(
    'ayarlar TESSERACT_YOLU tetik dur mesgul ekran_oku bolge ekran alan goruntu son_mesaji_temizle metin MESAJ_SECIMI metni_oku gri ikili cevap_uret mesaj yanit veri cevap AZAMI_CEVAP_UZUNLUGU elementi_bul referans sablon sol ust ARAMA_BOLGESI sonuc guven konum ESLESME_ESIGI iptal_kontrol butonu_bul_ve_tikla merkez UI_BEKLEME cevabi_yaz karakter YAZMA_ARALIGI ana_dongu SOHBET_BOLGESI TEXTBOX_RESIM GONDER_RESIM GONDERME_YONTEMI tetikle tus_testi windows_tus_dinle olay_yaz olay kanca windows_tus_okuyucu oku kodlar basili_tuslar ad kod onceki bekleyen simdiki tus aktif once_aktif secim kisayollar dinleyici kisayol OCR_DILI'.split(),
    'settings TESSERACT_PATH trigger_event stop_event busy_lock capture_screen region screen area image clean_message text MESSAGE_SELECTION read_text gray binary generate_reply message response data reply MAX_REPLY_LENGTH find_element reference template left top SEARCH_REGION result confidence location MATCH_THRESHOLD check_cancelled find_and_click center UI_DELAY type_reply character TYPING_INTERVAL run_cycle CHAT_REGION TEXTBOX_IMAGE SEND_IMAGE SEND_METHOD trigger_cycle key_test windows_key_listener log_event event hook windows_key_reader read_keys key_codes pressed_keys name code previous pending current key active previously_active mode hotkeys listener hotkey OCR_LANGUAGE'.split()
))
translations = {
"F9 ile tek tur çalışan, Windows / birincil monitör için sohbet MVP'si.": "Desktop chat MVP: one cycle per hotkey, Windows / primary monitor.",
"BGR görüntü ve ekran üzerindeki sol/üst başlangıç noktasını döndür.": "Return a BGR screenshot and its left/top screen offset.",
"Ekran bölgesinin boyutları pozitif olmalı.": "Screen region dimensions must be positive.",
"MESAJ_SECIMI 'bolge' veya 'son_paragraf' olmalı.": "MESSAGE_SELECTION must be 'region' or 'last_paragraph'.",
"API yanıtı bir JSON nesnesi olmalı.": "The API response must be a JSON object.",
"Ollama hatası:": "Ollama error:",
"LLM boş veya geçersiz cevap döndürdü.": "The LLM returned an empty or invalid reply.",
"LLM cevabı izin verilen uzunluğu aşıyor.": "The LLM reply exceeds the maximum length.",
"Eşiği geçen en iyi eşleşmenin ekran koordinatını bul; yoksa None.": "Return the best match above the threshold, or None.",
"Buton bulunamadı: referans resmi eksik (%s).": "Element not found: missing reference image (%s).",
"Buton bulunamadı: referans okunamıyor veya ayrıntı içermiyor.": "Element not found: unreadable or featureless reference image.",
"Buton bulunamadı: referans arama alanından büyük.": "Element not found: reference image exceeds the search region.",
"Buton bulunamadı: %s (eşleşme=%.3f).": "Element not found: %s (confidence=%.3f).",
"Kullanıcı durdurdu.": "Stopped by the user.",
"Tur başladı; ekran görüntüsü alınıyor.": "Cycle started; capturing the screen.",
"Ekran alındı; OCR çalışıyor.": "Screen captured; running OCR.",
"Okunabilir mesaj yok; bu tur sonlandırıldı.": "No readable message; cycle cancelled.",
"Mesaj okundu; LLM cevabı bekleniyor.": "Message read; waiting for the LLM reply.",
"Cevap kutuda kaldı; gönderilmedi. Yeniden F9 öncesi kutuyu kontrol et.": "Reply remains in the textbox; not sent. Check the textbox before pressing F9 again.",
"Gönderme aksiyonu uygulandı (teslim durumu kontrol edilmiyor).": "Send action completed (delivery is not verified).",
"Kısayol algılandı; önceki tur hâlâ çalışıyor.": "Hotkey detected; the previous cycle is still running.",
"Kısayol algılandı; tur başlatılıyor.": "Hotkey detected; starting a cycle.",
"Sadece tetik tuşlarını kontrol et; ekran okuma veya gönderme yapma.": "Test trigger keys only; do not read the screen or send messages.",
"WINDOWS TUŞ TESTİ: F9 / Ctrl+Alt+9 dene. Çıkış: F10 veya Ctrl+C. Mesaj gönderilmez.": "WINDOWS KEY TEST: try F9 / Ctrl+Alt+9. Exit: F10 or Ctrl+C. No messages will be sent.",
"Tuş algılandı: %s | %s": "Key detected: %s | %s",
"TUŞ TESTİ: F9, Fn+F9 veya 9 dene. Çıkış: Ctrl+C. Mesaj gönderilmez.": "KEY TEST: try F9, Fn+F9 or 9. Exit: Ctrl+C. No messages will be sent.",
"Klavye kancası kurmadan yalnızca beş tuşun basılı durumunu oku.": "Read only five key states without installing a keyboard hook.",
"20 ms aralıkla kontrol et; bir basış/bırakış için yalnızca bir tur başlat.": "Poll every 20 ms; trigger once per press/release sequence.",
"Tuş algılandı (Windows): %s | down": "Key detected (Windows): %s | down",
"Tuş algılandı (Windows): %s | up": "Key detected (Windows): %s | up",
"F10 algılandı; durduruluyor.": "F10 detected; stopping.",
"Kısayol basıldı (Windows). Tuşları bırak.": "Hotkey pressed (Windows). Release all hotkey keys.",
"Tetik başarılı (test); sohbet işlemi yapılmadı.": "Trigger successful (test); no chat action performed.",
"Windows tuş dinleyicisi durdu.": "The Windows key listener failed.",
"Masaüstü sohbet Alpha": "Desktop Chat Alpha",
"Sadece tuş algılamayı test et": "Test key detection without sending messages",
"3 saniye sonra kısayolsuz bir tur çalıştır ve gönder": "Run one cycle and send after a 3-second delay, without a hotkey",
"Gönderme yöntemi veya eşleşme eşiği geçersiz.": "Invalid send method or match threshold.",
"3 saniye sonra bir tur çalışacak ve cevap gönderilecek; hedef sohbeti aç. İptal: Ctrl+C.": "A cycle will run and send a reply in 3 seconds; open the target chat. Cancel: Ctrl+C.",
"Tek tur durduruldu.": "Single cycle stopped.",
"Tek tur başarısız; metin kutusunu kontrol et.": "Single cycle failed; check the textbox.",
"Tuş yöntemi: Windows doğrudan kontrol; keyboard kancası kullanılmıyor.": "Key input: Windows polling; no keyboard hook installed.",
"Hazır (v0.4). F9 veya Ctrl+Alt+9 basıp bırak: bir tur | F10 veya Ctrl+C: çıkış.": "Ready (v0.5). Press and release F9 or Ctrl+Alt+9: one cycle | F10 or Ctrl+C: exit.",
"Otomasyon durduruldu; kutuda kısmi metin kalmış olabilir.": "Automation stopped; partial text may remain in the textbox.",
"Bu tur sonlandırıldı. Yeni tur öncesi metin kutusunu kontrol et.": "Cycle failed. Check the textbox before starting another cycle.",
}
comments = [
    'Align screenshot pixels and mouse coordinates under Windows scaling.',
    'Configure DPI awareness before importing screen and mouse libraries.',
    'Create the MSS instance in the thread that captures the screen.',
    'Invert light text on a dark background for OCR.',
    'Newlines can accidentally send messages in some applications.',
    'imdecode + fromfile supports Unicode file paths on Windows.',
    'Check cancellation between characters and preserve Unicode characters.',
    'Assume an empty textbox; do not erase existing drafts.',
    'Ignore hotkeys while busy; allow only one cycle at a time.',
    'Do not log ordinary typing.',
    'Use only the currently-pressed high bit; the low bit is unreliable.',
    'Discard presses that started while a cycle was running.',
    'Use a separate callback for each registration to avoid cleanup collisions.',
    'Keep the listener alive after OCR, API, image or operating-system errors.',
]
source = (PROJECT / 'main.py').read_text(encoding='utf-8')
for old, new in translations.items():
    source = source.replace(old, new)
source = source.replace('--tus-testi', '--key-test').replace('--tek-tur', '--once')
source = source.replace('args.tus_testi', 'args.key_test').replace('args.tek_tur', 'args.once')
source = source.replace('"son_paragraf"', '"last_paragraph"').replace('"bolge"', '"region"').replace('"buton"', '"button"')
source = source.replace('format(mesaj=mesaj)', 'format(message=message)')
comment_iter = iter(comments)
tokens = []
for token in tokenize.generate_tokens(io.StringIO(source).readline):
    if token.type == tokenize.COMMENT:
        token = token._replace(string='# ' + next(comment_iter))
    elif token.type == tokenize.NAME:
        token = token._replace(string=names.get(token.string, token.string))
    # f-string expressions also need their local names translated.
    elif token.type == tokenize.STRING and token.string.startswith('f'):
        token = token._replace(string=token.string.replace("veri['error']", "data['error']"))
    tokens.append(token)
source = tokenize.untokenize(tokens)
assert not re.search('[\u0080-\uffff]', source), 'Untranslated text remains'
ast.parse(source)
(PROJECT / 'main.py').write_text(source, encoding='utf-8')

# Preserve the user's current settings without importing or executing their file.
old_settings = Path(r'C:\Users\bbkaa\Desktop\sohbet_alpha\ayarlar.py')
tree = ast.parse(old_settings.read_text(encoding='utf-8'))
values = {}
for node in tree.body:
    if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id != 'KOK':
        values[node.targets[0].id] = ast.unparse(node.value)
lines = ['"""English-only chat settings. Edit regions and reference images for your app."""',
         'from pathlib import Path', '', 'ROOT = Path(__file__).resolve().parent', '']
notes = {
    'SOHBET_BOLGESI': 'Physical pixels on the primary monitor. Include only the latest incoming message.',
    'ARAMA_BOLGESI': 'None searches the entire primary monitor; use a region to restrict matching.',
    'GONDERME_YONTEMI': 'Use "button" or "enter".',
    'MODEL': 'Must match a locally installed Ollama model.',
    'API_TIMEOUT': 'Connection and response timeouts in seconds.',
    'TESSERACT_YOLU': 'Full executable path, or None when Tesseract is available on PATH.',
    'MESAJ_SECIMI': 'Use "region" for one message, or "last_paragraph" as a layout-dependent heuristic.',
}
for name, value in values.items():
    if name in notes:
        lines.append('# ' + notes[name])
    value = value.replace('KOK /', 'ROOT /').replace('{mesaj}', '{message}')
    if name == 'GONDERME_YONTEMI':
        value = value.replace("'buton'", "'button'")
    if name == 'MESAJ_SECIMI':
        value = value.replace("'bolge'", "'region'").replace("'son_paragraf'", "'last_paragraph'")
    lines.append(names.get(name, name) + ' = ' + value)
(PROJECT / 'settings.py').write_text('\n'.join(lines) + '\n', encoding='utf-8')

# Update the existing regression checks to use the public English names.
test_path = ROOT / 'work' / 'verify_alpha.py'
tests = test_path.read_text(encoding='utf-8')
tests = tests.replace('Yan etkisiz kontrol: masaüstü, ağ ve OCR bağımlılıkları taklit edilir.',
                      'Side-effect-free checks with desktop, network and OCR mocks.')
for old, new in sorted(names.items(), key=lambda item: -len(item[0])):
    tests = re.sub(r'\b' + re.escape(old) + r'\b', new, tests)
tests = tests.replace('--tus-testi', '--key-test').replace('--tek-tur', '--once')
tests = tests.replace('Merhaba', 'Hello').replace('nasılsın?', 'how are you?').replace('İyiyim', 'Fine').replace('teşekkürler', 'thanks').replace('Selam', 'Hi').replace('ş', 'é')
test_path.write_text(tests, encoding='utf-8')
print('Translated source, migrated current settings, and updated regression checks.')
