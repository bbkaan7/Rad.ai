"""F9 ile tek tur çalışan, Windows / birincil monitör için sohbet MVP'si."""

import argparse
import ctypes
import logging
import os
import re
import threading
import time

# Ekran pikseli ile fare koordinatlarını Windows ölçeklemesinde hizala.
# Görsel/fare kütüphaneleri yüklenmeden önce çağrılmalıdır.
if os.name == "nt":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()

import cv2
import keyboard
import mss
import numpy as np
import pyautogui
import pytesseract
import requests

import ayarlar as a

log = logging.getLogger(__name__)
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.1
if a.TESSERACT_YOLU:
    pytesseract.pytesseract.tesseract_cmd = a.TESSERACT_YOLU

tetik = threading.Event()
dur = threading.Event()
mesgul = threading.Lock()


def ekran_oku(bolge=None):
    """BGR görüntü ve ekran üzerindeki sol/üst başlangıç noktasını döndür."""
    # MSS nesnesini, ekran görüntüsünü alan iş parçacığında oluştur.
    with mss.mss() as ekran:
        alan = dict(ekran.monitors[1] if bolge is None else bolge)
        if alan["width"] <= 0 or alan["height"] <= 0:
            raise ValueError("Ekran bölgesinin boyutları pozitif olmalı.")
        goruntu = np.array(ekran.grab(alan))
    return cv2.cvtColor(goruntu, cv2.COLOR_BGRA2BGR), (alan["left"], alan["top"])


def son_mesaji_temizle(metin):
    metin = metin.replace("\r\n", "\n").replace("\r", "\n").replace("\x0c", "").strip()
    if a.MESAJ_SECIMI == "son_paragraf":
        metin = re.split(r"\n\s*\n", metin)[-1]
    elif a.MESAJ_SECIMI != "bolge":
        raise ValueError("MESAJ_SECIMI 'bolge' veya 'son_paragraf' olmalı.")
    return " ".join(metin.split())


def metni_oku(goruntu):
    gri = cv2.cvtColor(goruntu, cv2.COLOR_BGR2GRAY)
    gri = cv2.resize(gri, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, ikili = cv2.threshold(gri, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Koyu temada açık yazıyı koyu yazı / açık arka plana çevir.
    if np.mean(ikili) < 127:
        ikili = cv2.bitwise_not(ikili)
    metin = pytesseract.image_to_string(
        ikili, lang=a.OCR_DILI, config=a.OCR_CONFIG, timeout=a.OCR_TIMEOUT
    )
    return son_mesaji_temizle(metin)


def cevap_uret(mesaj):
    yanit = requests.post(
        a.OLLAMA_URL,
        json={"model": a.MODEL, "prompt": a.PROMPT.format(mesaj=mesaj), "stream": False},
        timeout=a.API_TIMEOUT,
    )
    yanit.raise_for_status()
    veri = yanit.json()
    if not isinstance(veri, dict):
        raise ValueError("API yanıtı bir JSON nesnesi olmalı.")
    if veri.get("error"):
        raise ValueError(f"Ollama hatası: {veri['error']}")
    cevap = veri.get("response")
    if not isinstance(cevap, str) or not cevap.strip():
        raise ValueError("LLM boş veya geçersiz cevap döndürdü.")
    # Satır sonları bazı uygulamalarda erken gönderime yol açabilir.
    cevap = " ".join(cevap.split())
    if len(cevap) > a.AZAMI_CEVAP_UZUNLUGU:
        raise ValueError("LLM cevabı izin verilen uzunluğu aşıyor.")
    return cevap


def elementi_bul(referans):
    """Eşiği geçen en iyi eşleşmenin ekran koordinatını bul; yoksa None."""
    if not referans.is_file():
        log.error("Buton bulunamadı: referans resmi eksik (%s).", referans.name)
        return None
    # imdecode + fromfile, Windows'ta Türkçe dosya yollarını destekler.
    sablon = cv2.imdecode(np.fromfile(referans, dtype=np.uint8), cv2.IMREAD_GRAYSCALE)
    if sablon is None or float(sablon.std()) < 1:
        log.error("Buton bulunamadı: referans okunamıyor veya ayrıntı içermiyor.")
        return None
    goruntu, (sol, ust) = ekran_oku(a.ARAMA_BOLGESI)
    gri = cv2.cvtColor(goruntu, cv2.COLOR_BGR2GRAY)
    h, w = sablon.shape
    if h > gri.shape[0] or w > gri.shape[1]:
        log.error("Buton bulunamadı: referans arama alanından büyük.")
        return None
    sonuc = cv2.matchTemplate(gri, sablon, cv2.TM_CCOEFF_NORMED)
    _, guven, _, konum = cv2.minMaxLoc(sonuc)
    if not np.isfinite(guven) or guven < a.ESLESME_ESIGI:
        log.error("Buton bulunamadı: %s (eşleşme=%.3f).", referans.name, guven)
        return None
    return sol + konum[0] + w // 2, ust + konum[1] + h // 2


def iptal_kontrol():
    if dur.is_set():
        raise InterruptedError("Kullanıcı durdurdu.")
    pyautogui.failSafeCheck()


def butonu_bul_ve_tikla(referans):
    iptal_kontrol()
    merkez = elementi_bul(referans)
    if merkez is None:
        return False
    iptal_kontrol()
    pyautogui.click(*merkez)
    time.sleep(a.UI_BEKLEME)
    return True


def cevabi_yaz(cevap):
    # Karakterler arasında durdurma kontrolü yap; Türkçeyi sessizce kaybetme.
    for karakter in cevap:
        iptal_kontrol()
        if " " <= karakter <= "~":
            pyautogui.write(karakter, interval=a.YAZMA_ARALIGI)
        else:
            keyboard.write(karakter, exact=True)
            time.sleep(a.YAZMA_ARALIGI)


def ana_dongu():
    iptal_kontrol()
    log.info("Tur başladı; ekran görüntüsü alınıyor.")
    goruntu, _ = ekran_oku(a.SOHBET_BOLGESI)
    log.info("Ekran alındı; OCR çalışıyor.")
    mesaj = metni_oku(goruntu)
    if not mesaj:
        log.warning("Okunabilir mesaj yok; bu tur sonlandırıldı.")
        return
    log.info("Mesaj okundu; LLM cevabı bekleniyor.")
    cevap = cevap_uret(mesaj)
    iptal_kontrol()
    if not butonu_bul_ve_tikla(a.TEXTBOX_RESIM):
        return
    # MVP varsayımı: metin kutusu boş; kullanıcının taslağını silmeyiz.
    cevabi_yaz(cevap)
    time.sleep(a.UI_BEKLEME)
    iptal_kontrol()
    if a.GONDERME_YONTEMI == "enter":
        pyautogui.press("enter")
    elif not butonu_bul_ve_tikla(a.GONDER_RESIM):
        log.warning("Cevap kutuda kaldı; gönderilmedi. Yeniden F9 öncesi kutuyu kontrol et.")
        return
    log.info("Gönderme aksiyonu uygulandı (teslim durumu kontrol edilmiyor).")


def tetikle():
    # Meşgulken gelen F9 basışlarını kuyruğa alma; aynı anda tek tur çalışsın.
    if dur.is_set():
        return
    if not mesgul.acquire(blocking=False):
        log.info("Kısayol algılandı; önceki tur hâlâ çalışıyor.")
        return
    log.info("Kısayol algılandı; tur başlatılıyor.")
    tetik.set()


def tus_testi():
    """Sadece tetik tuşlarını kontrol et; ekran okuma veya gönderme yapma."""
    if os.name == "nt":
        log.info("WINDOWS TUŞ TESTİ: F9 / Ctrl+Alt+9 dene. Çıkış: F10 veya Ctrl+C. Mesaj gönderilmez.")
        try:
            windows_tus_dinle(test=True)
        except KeyboardInterrupt:
            dur.set()
        return

    def olay_yaz(olay):
        # Kullanıcının normal yazışmalarını kaydetme.
        if olay.name in {"f9", "f10", "9"}:
            log.info("Tuş algılandı: %s | %s", olay.name, olay.event_type)

    kanca = keyboard.hook(olay_yaz)
    try:
        log.info("TUŞ TESTİ: F9, Fn+F9 veya 9 dene. Çıkış: Ctrl+C. Mesaj gönderilmez.")
        threading.Event().wait()
    except KeyboardInterrupt:
        pass
    finally:
        keyboard.unhook(kanca)


def windows_tus_okuyucu():
    """Klavye kancası kurmadan yalnızca beş tuşun basılı durumunu oku."""
    oku = ctypes.windll.user32.GetAsyncKeyState
    oku.argtypes = [ctypes.c_int]
    oku.restype = ctypes.c_short
    kodlar = {"f9": 0x78, "f10": 0x79, "ctrl": 0x11, "alt": 0x12, "9": 0x39}

    def basili_tuslar():
        # Düşük bit güvenilir değil; sadece "şu anda basılı" bitini kullan.
        return {ad for ad, kod in kodlar.items() if oku(kod) & 0x8000}

    return basili_tuslar


def windows_tus_dinle(test=False):
    """20 ms aralıkla kontrol et; bir basış/bırakış için yalnızca bir tur başlat."""
    try:
        oku = windows_tus_okuyucu()
        onceki = set()
        bekleyen = False
        while not dur.wait(0.02):
            simdiki = oku()
            if test:
                for tus in sorted(simdiki - onceki):
                    log.info("Tuş algılandı (Windows): %s | down", tus)
                for tus in sorted(onceki - simdiki):
                    log.info("Tuş algılandı (Windows): %s | up", tus)
            if "f10" in simdiki:
                log.info("F10 algılandı; durduruluyor.")
                dur.set()
                return
            aktif = "f9" in simdiki or {"ctrl", "alt", "9"}.issubset(simdiki)
            once_aktif = "f9" in onceki or {"ctrl", "alt", "9"}.issubset(onceki)
            if aktif and not once_aktif:
                # İşlem sırasında başlayan basışları sonraki tura taşıma.
                bekleyen = test or not mesgul.locked()
                if not test:
                    log.info("Kısayol basıldı (Windows). Tuşları bırak.")
            if bekleyen and not simdiki.intersection({"f9", "ctrl", "alt", "9"}):
                bekleyen = False
                if test:
                    log.info("Tetik başarılı (test); sohbet işlemi yapılmadı.")
                else:
                    tetikle()
            onceki = simdiki
    except Exception:
        log.exception("Windows tuş dinleyicisi durdu.")
        dur.set()


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
    parser = argparse.ArgumentParser(description="Masaüstü sohbet Alpha")
    secim = parser.add_mutually_exclusive_group()
    secim.add_argument("--tus-testi", action="store_true", help="Sadece tuş algılamayı test et")
    secim.add_argument("--tek-tur", action="store_true", help="3 saniye sonra kısayolsuz bir tur çalıştır ve gönder")
    args = parser.parse_args()
    if args.tus_testi:
        tus_testi()
        return
    if a.GONDERME_YONTEMI not in {"buton", "enter"} or not 0 < a.ESLESME_ESIGI <= 1:
        raise ValueError("Gönderme yöntemi veya eşleşme eşiği geçersiz.")
    kisayollar = []
    dinleyici = None
    try:
        if args.tek_tur:
            log.info("3 saniye sonra bir tur çalışacak ve cevap gönderilecek; hedef sohbeti aç. İptal: Ctrl+C.")
            time.sleep(3)
            try:
                ana_dongu()
            except (pyautogui.FailSafeException, InterruptedError):
                log.warning("Tek tur durduruldu.")
            except Exception:
                log.exception("Tek tur başarısız; metin kutusunu kontrol et.")
            return
        if os.name == "nt":
            dinleyici = threading.Thread(target=windows_tus_dinle, daemon=True)
            dinleyici.start()
            log.info("Tuş yöntemi: Windows doğrudan kontrol; keyboard kancası kullanılmıyor.")
        else:
            # Her kayıt ayrı callback kullanmalı; keyboard temizliğinde çakışmasın.
            kisayollar.append(keyboard.add_hotkey("f9", lambda: tetikle(), trigger_on_release=True))
            kisayollar.append(keyboard.add_hotkey("ctrl+alt+9", lambda: tetikle(), trigger_on_release=True))
            kisayollar.append(keyboard.add_hotkey("f10", dur.set, trigger_on_release=True))
        log.info("Hazır (v0.4). F9 veya Ctrl+Alt+9 basıp bırak: bir tur | F10 veya Ctrl+C: çıkış.")
        while not dur.is_set():
            if not tetik.wait(timeout=0.1):
                continue
            tetik.clear()
            try:
                ana_dongu()
            except (pyautogui.FailSafeException, InterruptedError):
                log.warning("Otomasyon durduruldu; kutuda kısmi metin kalmış olabilir.")
                dur.set()
            except Exception:
                # OCR, API, görsel ve işletim sistemi hataları dinleyiciyi çökertmesin.
                log.exception("Bu tur sonlandırıldı. Yeni tur öncesi metin kutusunu kontrol et.")
            finally:
                mesgul.release()
    except KeyboardInterrupt:
        dur.set()
    finally:
        dur.set()
        if dinleyici is not None:
            dinleyici.join(timeout=1)
        for kisayol in kisayollar:
            keyboard.remove_hotkey(kisayol)


if __name__ == "__main__":
    main()
