#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
notify_floor_alerts.py

Нотификатор floor gap с дополнительными категориями:
— “Трэш” для всех новых офферов в топ-5 (независимо от цены),
— “Полутреш” для офферов ≤ floor * 0.98 (−2%),
— “Супер важный” для офферов ≤ floor * 0.96 (−4%).
"""

import sqlite3
import time
import logging
import json
import signal
import sys
from pathlib import Path

from utils.config import load_config
from utils.session_manager import SessionManager

# --- Настройки ---
cfg = load_config("prod")
DB_PATH = Path("getgems_offers.db")
TABLE = "nft_offers"

TRASH_COUNT = 5               # число офферов в топ-5 для “трэша”
SUPER_FACTOR = 0.96           # −4%
HALF_FACTOR  = 0.98           # −2%

BOT_TOKEN = cfg["bot_token"]
API_URL   = f"https://api.telegram.org/bot{BOT_TOKEN}"
SEND_URL  = API_URL + "/sendMessage"
UPD_URL   = API_URL + "/getUpdates"
CHATS_FILE = Path("chats.json")
DELAY      = cfg.get("notify_interval_seconds", 60)

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
        for u in r.json().get("result", []):
            if "message" in u:
                ks.add(u["message"]["chat"]["id"])
            if "callback_query" in u:
                ks.add(u["callback_query"]["from"]["id"])
        if r.json().get("result"):
            last = r.json()["result"][-1]["update_id"]
            session.get(f"{UPD_URL}?offset={last+1}")
    except Exception as e:
        logger.warning("getUpdates error: %s", e)
    save_chats(ks)
    logger.info("Known chats: %d", len(ks))
    return ks

def fetch_offers(conn: sqlite3.Connection) -> list:
    cur = conn.cursor()
    cur.execute(f"""
        SELECT token_address, sale_price, sale_fee, royalty_amount, fee_total, created_at
          FROM {TABLE}
         WHERE sale_price IS NOT NULL
         ORDER BY (sale_price + sale_fee) ASC
         LIMIT {TRASH_COUNT}
    """)
    return cur.fetchall()

def compute_thresholds(prices: list) -> tuple:
    if len(prices) < 2:
        return None, None
    return prices[0], prices[1]

def make_message(url: str, rec: dict, label: str) -> str:
    lines = [f"{label}\n{url}"]
    for k, v in rec.items():
        lines.append(f"{k}: {v}")
    return "\n".join(lines)

def send_all(chats: set, text: str):
    for cid in chats:
        try:
            session.post(
                SEND_URL,
                json={"chat_id": cid, "text": text, "disable_web_page_preview": True}
            )
        except Exception as e:
            logger.error("Send error to %s: %s", cid, e)

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
    seen_trash = set()
    seen_half  = set()
    seen_super = set()

    while True:
        try:
            chats = update_chats()
            rows = fetch_offers(conn)
            # список эффективных цен
            effs = [p + f for _, p, f, _, _, _ in rows]
            floor, second = compute_thresholds(effs) or (None, None)
            # обходим топ-5
            for idx, (token, p, f, ramt, ftot, created) in enumerate(rows, start=1):
                eff = p + f
                url = f"https://getgems.io/collection/{cfg['collection_address']}/{token}?modalId=sale_info"
                rec = {
                    "sale_price": p,
                    "sale_fee": f,
                    "royalty_amount": ramt,
                    "fee_total": ftot,
                    "created_at": created
                }
                # Трэш: все новые в топ-5
                if token not in seen_trash:
                    label = f"🗑️ Трэш-алерт: новое предложение #{idx}"
                    send_all(chats, make_message(url, rec, label))
                    seen_trash.add(token)
                # Полутреш и супер важный только если есть пороги
                if floor is not None and second is not None:
                    super_thr = floor * SUPER_FACTOR
                    half_thr  = floor * HALF_FACTOR
                    if eff <= half_thr and token not in seen_half:
                        label = "⚠️ Полутреш-алерт (−2%)"
                        send_all(chats, make_message(url, rec, label))
                        seen_half.add(token)
                    if eff <= super_thr and token not in seen_super:
                        label = "🔥 Супер-алерт (−4%)"
                        send_all(chats, make_message(url, rec, label))
                        seen_super.add(token)
        except Exception as e:
            logger.exception("Notification loop error: %s", e)

        time.sleep(DELAY)

if __name__ == "__main__":
    main()
