# -*- coding: utf-8 -*-
"""
Bülten Almanya - Gurbetçi Haber Takip Botu
--------------------------------------------
Google News RSS ve DW Türkçe RSS üzerinden Almanya'da yaşayan Türkleri
ve genel Türkiye gündemini tarar, filtreler ve Telegram'a bildirim gönderir.
"""

import feedparser
import requests
import json
import os
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote
from calendar import timegm

# ============ AYARLAR ============

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8889739318:AAEYbJ8cy8UNeqwA00C_DeZuEoECXqqfxN4")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "6841282915")

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(SCRIPT_DIR, "seen_items.json")

# Bir haberin en fazla kaç saat önce yayınlanmış olabileceği (bundan eskisi elenir)
FRESHNESS_HOURS = 6

# ---- Kategori 1: Almanya'daki Türkleri ilgilendiren haberler ----
GERMANY_QUERIES = [
    "Almanya Türkleri",
    "gurbetçi Almanya",
    "Almanya'da Türk",
    "Almanya yaşayan Türkler",
    "Berlin Türkler",
    "Almanya Türk toplumu",
    "Almanya vize Türk",
    "Almanya oturma izni",
    "Almanya Türk işçi",
]

# ---- Kategori 2: Genel Türkiye gündemi / son dakika ----
TURKEY_AGENDA_QUERIES = [
    "Türkiye son dakika",
    "Türkiye gündem",
    "Türkiye ekonomi son dakika",
    "Türkiye siyaset son dakika",
]

EXTRA_FEEDS = [
    ("https://rss.dw.com/rdf/rss-tur-all", "🇩🇪 Almanya Türkleri"),
]

# Bir haberin alakalı sayılması için (Almanya kategorisi) geçmesi gereken kelimeler
GERMANY_INCLUDE_KEYWORDS = [
    "almanya", "alman", "berlin", "köln", "koln", "münih", "munih",
    "stuttgart", "frankfurt", "hamburg", "gurbetçi", "gurbetci",
    "göçmen", "gocmen", "diaspora", "vize", "oturma izni", "sınır dışı",
    "sinir disi", "işçi", "isci", "türk toplumu", "turk toplumu",
]

# Kesinlikle istenmeyen içerik türleri (köşe yazısı, analiz, spor vb.)
EXCLUDE_KEYWORDS = [
    "maç sonucu", "mac sonucu", "gol attı", "gol atti", "transfer haberi",
    "hava durumu", "köşe yazısı", "kose yazisi", "yorumu:", "analiz:",
    "podcast", "canlı yayın", "canli yayin", "burç yorum", "burc yorum",
    "ne izlesek", "haftalık gündem özeti",
]

# ============ YARDIMCI FONKSİYONLAR ============

def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()


def save_seen(seen_ids):
    trimmed = list(seen_ids)[-3000:]
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(trimmed, f, ensure_ascii=False)


def normalize(text):
    return (text or "").lower()


def is_excluded(title, summary):
    text = normalize(title) + " " + normalize(summary)
    return any(bad in text for bad in EXCLUDE_KEYWORDS)


def is_germany_relevant(title, summary):
    text = normalize(title) + " " + normalize(summary)
    return any(good in text for good in GERMANY_INCLUDE_KEYWORDS)


def build_google_news_url(query):
    # "when:6h" -> Google News'e son 6 saat filtresini kendisi uygular
    q = quote(f"{query} when:{FRESHNESS_HOURS}h")
    return f"https://news.google.com/rss/search?q={q}&hl=tr&gl=DE&ceid=DE:tr"


def is_fresh_enough(entry):
    """published_parsed yoksa güvenlik payı ile geçerli say."""
    struct = entry.get("published_parsed")
    if not struct:
        return True
    published_dt = datetime.fromtimestamp(timegm(struct), tz=timezone.utc)
    cutoff = datetime.now(timezone.utc) - timedelta(hours=FRESHNESS_HOURS + 1)
    return published_dt >= cutoff


def fetch_category(queries, category_label, apply_germany_filter):
    entries = []
    for q in queries:
        url = build_google_news_url(q)
        try:
            parsed = feedparser.parse(url)
            for entry in parsed.entries:
                if not is_fresh_enough(entry):
                    continue
                title = entry.get("title", "").strip()
                summary = re.sub("<[^<]+?>", "", entry.get("summary", "")).strip()
                if is_excluded(title, summary):
                    continue
                if apply_germany_filter and not is_germany_relevant(title, summary):
                    continue
                entries.append({
                    "id": entry.get("id") or entry.get("link"),
                    "title": title,
                    "link": entry.get("link", "").strip(),
                    "summary": summary,
                    "source": parsed.feed.get("title", "Google News"),
                    "category": category_label,
                })
        except Exception as e:
            print(f"[UYARI] Feed alınamadı: {url} -> {e}")
    return entries


def fetch_all_entries():
    all_entries = []
    all_entries += fetch_category(GERMANY_QUERIES, "🇩🇪 Almanya Türkleri", apply_germany_filter=False)
    all_entries += fetch_category(TURKEY_AGENDA_QUERIES, "🇹🇷 Türkiye Gündemi", apply_germany_filter=False)

    for url, label in EXTRA_FEEDS:
        try:
            parsed = feedparser.parse(url)
            for entry in parsed.entries:
                if not is_fresh_enough(entry):
                    continue
                title = entry.get("title", "").strip()
                summary = re.sub("<[^<]+?>", "", entry.get("summary", "")).strip()
                if is_excluded(title, summary):
                    continue
                all_entries.append({
                    "id": entry.get("id") or entry.get("link"),
                    "title": title,
                    "link": entry.get("link", "").strip(),
                    "summary": summary,
                    "source": parsed.feed.get("title", "DW Türkçe"),
                    "category": label,
                })
        except Exception as e:
            print(f"[UYARI] Feed alınamadı: {url} -> {e}")

    return all_entries


def build_search_links(title):
    q = quote(title[:80])
    x_url = f"https://twitter.com/search?q={q}&f=live"
    tiktok_url = f"https://www.tiktok.com/search?q={q}"
    return x_url, tiktok_url


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
    category = item["category"]
    x_url, tiktok_url = build_search_links(title)
    return (
        f"{category}\n"
        f"📰 <b>{title}</b>\n\n"
        f"🔗 {link}\n"
        f"📌 Kaynak: {source}\n\n"
        f"🔎 <a href=\"{x_url}\">X'te ara</a> | 🎵 <a href=\"{tiktok_url}\">TikTok'ta ara</a>"
    )


# ============ ANA AKIŞ ============

def main():
    print(f"[{datetime.now()}] Tarama başlıyor...")

    seen = load_seen()
    entries = fetch_all_entries()
    print(f"Toplam {len(entries)} haber tarandı (tazelik ve filtre sonrası).")

    new_items = []
    for item in entries:
        if not item["id"] or item["id"] in seen:
            continue
        new_items.append(item)
        seen.add(item["id"])

    print(f"{len(new_items)} yeni haber bulundu.")

    for item in new_items:
        send_telegram_message(format_message(item))

    save_seen(seen)
    print(f"[{datetime.now()}] Tarama tamamlandı.\n")


if __name__ == "__main__":
    main()
