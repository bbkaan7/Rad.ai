# Masaüstü sohbet otomasyonu — Alpha

Python 3.10+; Windows ve birincil monitör hedeflenmiştir. F9 bırakıldığında bir
mesaj okunur, Ollama'dan cevap alınır, resimle bulunan kutuya yazılır ve gönderilir.
İşlem boyunca gelen diğer F9 basışları yok sayılır. Sonraki tur için tekrar F9 gerekir.

## Kurulum

Bu klasörde terminal aç:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Tesseract OCR motorunu ayrıca kur; `pytesseract` yalnızca Python bağlantısıdır.
`tur` ve `eng` dil dosyalarını yükle. Motor PATH'te değilse `ayarlar.py` içindeki
`TESSERACT_YOLU` değerine tesseract.exe yolunu yaz.

Ollama'yı kurup çalıştır ve seçtiğin modeli indir. Örnek:

```powershell
ollama pull llama3.2
```

Yerel servis zaten çalışmıyorsa ayrı terminalde `ollama serve` çalıştır.
Başka model seçersen `MODEL` ayarını değiştir.

## Ekranı hazırlama

1. Sohbet uygulamasını birincil monitöre getir.
2. `SOHBET_BOLGESI` değerlerini son gelen mesajı kapsayacak şekilde değiştir.
   Koordinatlar fiziksel ekran pikselleridir: left/top/width/height.
3. `templates/README.md` tarifine göre `textbox.png` ve `send_btn.png` ekle.
4. İstersen `ARAMA_BOLGESI` ile görsel aramayı sohbet penceresine sınırla.
   Buton konumları ezberlenmez; her tıklamada yeniden görsel eşleştirme yapılır.
5. Metin kutusunu boş bırak, hedef sohbeti açık tut ve çalışırken başka pencereye geçme.

```powershell
.\.venv\Scripts\python.exe main.py
```

- **F9:** bir tur çalıştır.
- **F10 / Ctrl+C:** çık. F10 yeni ekran aksiyonlarını engeller; sürmekte olan
  OCR/HTTP çağrısını kesmez, bu çağrı dönünce veya zaman aşımına uğrayınca çıkılır.
- Fareyi birincil ekranın köşesine götürmek PyAutoGUI fail-safe mekanizmasını tetikler.
- `GONDERME_YONTEMI = "enter"` seçilirse gönderme butonu yerine Enter kullanılır.

## Alpha sınırları

- Düz OCR, mesaj balonlarını ve göndereni güvenilir biçimde ayıramaz. Varsayılan
  `MESAJ_SECIMI = "bolge"`, seçilen alanı tek mesaj kabul eder ve satırları birleştirir.
  Bu nedenle alan son gelen mesajı kapsamalıdır. `son_paragraf` seçeneği sadece OCR
  çıktısındaki son boş satırla ayrılmış bloğu alır; tüm sohbet için kesin çözüm değildir.
  Otomatik mesaj balonu/konuşmacı ayrımı bu MVP'de yoktur.
- `cv2.matchTemplate` aynı ölçek ve temada çalışır. Eşik altındaki, eksik,
  okunamayan veya düz renkli referanslar `Buton bulunamadı` hatasıyla turu bitirir.
  Benzer görseller varsa en iyi eşleşme yanlış öğe olabilir; arama alanını daralt.
- ASCII karakterleri `pyautogui.write(..., interval=0.05)` yazar. Türkçe ve diğer
  Unicode karakterler `keyboard.write(..., exact=True)` ile yazılır. Klavye düzeni
  ve hedef uygulama davranışını önce boş bir test sohbetinde dene.
- Gönder butonu yazımdan sonra tekrar aranır; bulunamazsa cevap kutuda kalır.
  Hata/iptal sonrası yeniden F9'a basmadan kutuyu kontrol et. Taslaklar silinmez.
- Tekrar eden mesajlar takip edilmez; her F9 yeni işlem yapar. Teslim doğrulaması,
  pencere kimliği doğrulaması ve arka plandaki kapalı pencerelere yazma yoktur.
- Kod burada gerçek sohbet ekranı, Tesseract ve Ollama ile uçtan uca denenmemiştir.

## Dosyalar

- `ayarlar.py`: bölgeler, model, prompt, eşik ve süreler.
- `main.py`: ekran, OCR, API, görsel eşleştirme, yazma ve F9 dinleyicisi.
- `requirements.txt`: Python bağımlılıkları (tekrarlanabilir sürüm kilidi değildir).

## Resmî kaynaklar

- [Ollama generate API](https://docs.ollama.com/api/generate): `stream: false` ve `response`.
- [PyAutoGUI klavye](https://pyautogui.readthedocs.io/en/latest/keyboard.html): yazma aralığı.
- [OpenCV eşleştirme](https://docs.opencv.org/4.x/d4/dc6/tutorial_py_template_matching.html).
- [pytesseract](https://github.com/madmaze/pytesseract): motor kurulumu ve OCR.
- [keyboard](https://github.com/boppreh/keyboard): kısayol ve Unicode yazma.
