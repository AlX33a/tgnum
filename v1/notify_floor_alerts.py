#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import time
import logging
import json
import signal
import sys
from pathlib import Path

from utils.config import load_config
from utils.session_manager import SessionManager

cfg = load_config("prod")
DB_PATH = Path("getgems_offers.db")
TABLE = "nft_offers"

SUPER_IMPORTANT_FACTOR = 0.96  # −4%
HALF_THRESHOLD_FACTOR     = 0.98  # −2%

BOT_TOKEN = cfg["bot_token"]
API_URL   = f"https://api.telegram.org/bot{BOT_TOKEN}"
SEND_URL  = API_URL + "/sendMessage"
UPD_URL   = API_URL + "/getUpdates"
CHATS_FILE = Path("chats.json")
DELAY      = cfg.get("notify_interval_seconds", 60)

# Сессия сама выберет таймаут для Telegram по URL
session = SessionManager(cfg)

logging.basicConfig(
    level=getattr(logging, cfg["log_level"].upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("floor_alerts.log", encoding="utf-8")
    ]
)
logger = logging.getLogger(__name__)

def load_chats() -> set:
    if CHATS_FILE.exists():
        return set(json.loads(CHATS_FILE.read_text(encoding="utf-8")))
    return set()

def save_chats(chats: set):
    CHATS_FILE.write_text(json.dumps(list(chats)), encoding="utf-8")

def update_chats() -> set:
    ks = load_chats()
    try:
        r = session.get(UPD_URL)
        r.raise_for_status()
        items = r.json().get("result", [])
        for upd in items:
            if "message" in upd:
                ks.add(upd["message"]["chat"]["id"])
            if "callback_query" in upd:
                ks.add(upd["callback_query"]["from"]["id"])
        if items:
            last_id = items[-1]["update_id"]
            session.get(f"{UPD_URL}?offset={last_id+1}")
    except Exception as e:
        logger.warning("getUpdates error: %s", e)
    save_chats(ks)
    logger.info("Known chats: %d", len(ks))
    return ks

def fetch_offers(conn: sqlite3.Connection) -> list:
    cur = conn.cursor()
    cur.execute(f"""
        SELECT id, token_address, sale_price, sale_fee,
               royalty_amount, fee_total, updated_at, created_at
          FROM {TABLE}
         WHERE sale_price IS NOT NULL
    """)
    return cur.fetchall()

def send_all(chats: set, text: str):
    for cid in chats:
        try:
            session.post(
                SEND_URL,
                json={"chat_id": cid, "text": text, "disable_web_page_preview": True}
            )
        except Exception as e:
            logger.error("Send error to %s: %s", cid, e)

def make_message(url: str, rec: dict, level: str) -> str:
    lines = [f"{level}\n{url}"]
    for k, v in rec.items():
        lines.append(f"{k}: {v}")
    return "\n".join(lines)

def shutdown(signum, frame):
    logger.info("Signal %s received, shutdown", signum)
    chats = load_chats()
    send_all(chats, "⚠️ Нотификатор floor gap выключается")
    sys.exit(0)

def main():
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    if not DB_PATH.exists():
        logger.error("DB not found: %s", DB_PATH)
        return

    chats = update_chats()
    if chats:
        send_all(chats, "🔔 Нотификатор floor gap запущен")

    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    notified = set()

    while True:
        try:
            chats = update_chats()
            rows = fetch_offers(conn)
            recs = []
            for oid, token, p, fee, roy, ft, upd, crt in rows:
                eff = p + fee
                recs.append((oid, token, eff, {
                    "sale_price": p,
                    "sale_fee": fee,
                    "royalty_amount": roy,
                    "fee_total": ft,
                    "updated_at": upd,
                    "created_at": crt
                }))

            effs = sorted(r[2] for r in recs)
            if len(effs) >= 2:
                floor, second = effs[0], effs[1]
                super_thr = floor * SUPER_IMPORTANT_FACTOR
                half_thr  = floor * HALF_THRESHOLD_FACTOR

                for oid, token, eff, rec in recs:
                    if oid in notified:
                        continue
                    url = f"https://getgems.io/collection/{cfg['collection_address']}/{token}?modalId=sale_info"
                    if eff <= super_thr:
                        msg = make_message(url, rec, "🔥 СУПЕР ВАЖНЫЙ АЛЕРТ (−4%)")
                        send_all(chats, msg)
                        notified.add(oid)
                    elif eff <= half_thr:
                        msg = make_message(url, rec, "⚠️ ПОЛУТРЕШ АЛЕРТ (−2%)")
                        send_all(chats, msg)
                        notified.add(oid)
        except Exception as e:
            logger.exception("Notification loop error: %s", e)

        time.sleep(DELAY)

if __name__ == "__main__":
    main()
