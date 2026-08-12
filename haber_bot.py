# -*- coding: utf-8 -*-
"""
Bülten Almanya - Gurbetçi Haber Takip Botu
--------------------------------------------
Google News RSS ve DW Türkçe RSS üzerinden Almanya'da yaşayan Türkleri
ilgilendiren haberleri tarar, anahtar kelime bazlı filtreler ve
Telegram üzerinden bildirim gönderir.

Çalıştırma: python haber_bot.py
(Windows Görev Zamanlayıcı ile her 15-20 dakikada bir otomatik çalıştırılması önerilir)
"""

import feedparser
import requests
import json
import os
import re
from datetime import datetime
from urllib.parse import quote

# ============ AYARLAR ============

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8889739318:AAEYbJ8cy8UNeqwA00C_DeZuEoECXqqfxN4")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "6841282915")

# Script'in dosya konumuna göre "daha önce gönderilenler" listesini saklar
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(SCRIPT_DIR, "seen_items.json")

# Google News RSS için arama sorguları (Türkçe, Almanya odaklı)
# Her biri ayrı bir RSS akışı olarak taranır
GOOGLE_NEWS_QUERIES = [
    "Almanya Türkleri",
    "gurbetçi Almanya",
    "Almanya'da Türk",
    "Almanya yaşayan Türkler",
    "Berlin Türkler",
    "Almanya Türk toplumu",
    "Almanya'da Türk vatandaşı",
    "Almanya vize Türk",
    "Almanya oturma izni",
    "Almanya Türk işçi",
]

# Ek sabit RSS kaynakları (site geneli, sonra anahtar kelimeyle filtrelenir)
EXTRA_FEEDS = [
    "https://rss.dw.com/rdf/rss-tur-all",  # DW Türkçe - genel akış
]

# Bir haberin "gurbetçiyi ilgilendirir" sayılması için başlık/özette
# aranacak anahtar kelimeler (en az biri geçmeli)
INCLUDE_KEYWORDS = [
    "almanya", "alman", "berlin", "köln", "koln", "münih", "munih",
    "stuttgart", "frankfurt", "hamburg", "gurbetçi", "gurbetci",
    "göçmen", "gocmen", "diaspora", "vize", "oturma izni", "sınır dışı",
    "sinir disi", "işçi", "isci", "türk toplumu", "turk toplumu",
]

# Kesinlikle istenmeyen konular (bunlardan biri geçerse ELENIR)
EXCLUDE_KEYWORDS = [
    "maç sonucu", "mac sonucu", "gol attı", "gol atti", "transfer haberi",
    "hava durumu",
]

# ============ YARDIMCI FONKSİYONLAR ============

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen_ids):
    # Dosyanın sonsuza kadar büyümesini engellemek için son 2000 kaydı tut
    trimmed = list(seen_ids)[-2000:]
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False)


def normalize(text):
    return (text or "").lower()


def is_relevant(title, summary):
    text = normalize(title) + " " + normalize(summary)

    for bad in EXCLUDE_KEYWORDS:
        if bad in text:
            return False

    for good in INCLUDE_KEYWORDS:
        if good in text:
            return True

    return False


def build_google_news_url(query):
    q = quote(query)
    return f"https://news.google.com/rss/search?q={q}&hl=tr&gl=DE&ceid=DE:tr"


def fetch_all_entries():
    feeds = [build_google_news_url(q) for q in GOOGLE_NEWS_QUERIES] + EXTRA_FEEDS
    all_entries = []
    for url in feeds:
        try:
            parsed = feedparser.parse(url)
            for entry in parsed.entries:
                all_entries.append({
                    "id": entry.get("id") or entry.get("link"),
                    "title": entry.get("title", "").strip(),
                    "link": entry.get("link", "").strip(),
                    "summary": re.sub("<[^<]+?>", "", entry.get("summary", "")).strip(),
                    "source": parsed.feed.get("title", "Bilinmeyen Kaynak"),
                    "published": entry.get("published", ""),
                })
        except Exception as e:
            print(f"[UYARI] Feed alınamadı: {url} -> {e}")
    return all_entries


def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, data=payload, timeout=15)
        if r.status_code != 200:
            print(f"[HATA] Telegram gönderim hatası: {r.status_code} {r.text}")
    except Exception as e:
        print(f"[HATA] Telegram bağlantı hatası: {e}")


def format_message(item):
    title = item["title"]
    link = item["link"]
    source = item["source"]
    return f"📰 <b>{title}</b>\n\n🔗 {link}\n📌 Kaynak: {source}"


# ============ ANA AKIŞ ============

def main():
    print(f"[{datetime.now()}] Tarama başlıyor...")

    if TELEGRAM_CHAT_ID == "BURAYA_CHAT_ID_GELECEK":
        print("[HATA] Önce TELEGRAM_CHAT_ID değerini ayarla!")
        return

    seen = load_seen()
    entries = fetch_all_entries()
    print(f"Toplam {len(entries)} haber tarandı.")

    new_relevant = []
    for item in entries:
        if not item["id"] or item["id"] in seen:
            continue
        if is_relevant(item["title"], item["summary"]):
            new_relevant.append(item)
        seen.add(item["id"])

    print(f"{len(new_relevant)} yeni ve alakalı haber bulundu.")

    for item in new_relevant:
        send_telegram_message(format_message(item))

    save_seen(seen)
    print(f"[{datetime.now()}] Tarama tamamlandı.\n")


if __name__ == "__main__":
    main()
