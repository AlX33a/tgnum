#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
notify_offers.py

Раз в минуту проверяет базу и рассылает уведомления о новых верифицированных офферах
во все чаты, которые когда-либо писали боту.
"""

import sqlite3
import requests
import time
import logging
import json
from pathlib import Path

# --- Настройки ---
DB_PATH    = Path("getgems_offers.db")
TABLE      = "nft_offers_verified"
PRICE_TH   = 886.0
BOT_TOKEN  = ""
API_URL    = f"https://api.telegram.org/bot{BOT_TOKEN}"
SEND_URL   = API_URL + "/sendMessage"
UPDATES_URL= API_URL + "/getUpdates"
# Файл для хранения чат-ID между запусками
CHATS_FILE = Path("chats.json")

# --- Логирование ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("notify_offers.log", encoding="utf-8")]
)
logger = logging.getLogger(__name__)

def load_known_chats():
    if CHATS_FILE.exists():
        return set(json.loads(CHATS_FILE.read_text()))
    return set()

def save_known_chats(chats):
    CHATS_FILE.write_text(json.dumps(list(chats)))

def update_known_chats():
    """Вызывать getUpdates, собирать chat_id всех новых обращений."""
    known = load_known_chats()
    try:
        resp = requests.get(UPDATES_URL, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        for upd in data.get("result", []):
            if "message" in upd:
                cid = upd["message"]["chat"]["id"]
                known.add(cid)
            if "callback_query" in upd:
                cid = upd["callback_query"]["from"]["id"]
                known.add(cid)
        # сброс offset, чтобы получать все апдейты заново
        if data.get("result"):
            last_id = data["result"][-1]["update_id"]
            requests.get(UPDATES_URL + f"?offset={last_id+1}", timeout=5)
    except Exception as e:
        logger.error("Ошибка getUpdates: %s", e, exc_info=True)
    save_known_chats(known)
    logger.info("Всего известных чатов: %d", len(known))
    return known

def ensure_sent_column(conn):
    cur = conn.execute(f"PRAGMA table_info({TABLE})")
    cols = [r[1] for r in cur.fetchall()]
    if "sent" not in cols:
        logger.info("Добавляю колонку sent")
        conn.execute(f"ALTER TABLE {TABLE} ADD COLUMN sent INTEGER DEFAULT 0")
        conn.commit()

def fetch_new_offers(conn):
    ensure_sent_column(conn)
    cur = conn.execute(f"""
        SELECT id, offer_url, full_price_tons
        FROM {TABLE}
        WHERE verify = 1
          AND full_price_tons < ?
          AND sent = 0
    """, (PRICE_TH,))
    rows = cur.fetchall()
    logger.info("Найдено %d новых офферов ниже %.2f TON", len(rows), PRICE_TH)
    return rows

def mark_sent(conn, oid):
    conn.execute(f"UPDATE {TABLE} SET sent = 1 WHERE id = ?", (oid,))
    conn.commit()

def send_to_all(chats, url, price):
    text = f"🔔 NFT-оффер: {url}\n💰 Цена: {price:.2f} TON"
    for cid in chats:
        payload = {"chat_id": cid, "text": text, "disable_web_page_preview": True}
        try:
            r = requests.post(SEND_URL, json=payload, timeout=5)
            if r.status_code != 200:
                logger.warning("Не удалось отправить в %s: %s", cid, r.text)
        except Exception as e:
            logger.error("Ошибка отправки в %s: %s", cid, e)

def main():
    if not DB_PATH.exists():
        logger.error("База не найдена: %s", DB_PATH)
        return
    known_chats = update_known_chats()
    conn = sqlite3.connect(DB_PATH)
    while True:
        try:
            # Обновляем список чатов перед каждой рассылкой
            known_chats = update_known_chats()
            offers = fetch_new_offers(conn)
            for oid, url, price in offers:
                send_to_all(known_chats, url, price)
                mark_sent(conn, oid)
        except Exception as e:
            logger.exception("Ошибка в основном цикле")
        time.sleep(60)

if __name__ == "__main__":
    main()
