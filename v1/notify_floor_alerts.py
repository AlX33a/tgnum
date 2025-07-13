#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sqlite3
import time
import logging
import json
from pathlib import Path
from utils.session_manager import SessionManager

def load_chats(chats_file):
    if chats_file.exists():
        return set(json.loads(chats_file.read_text()))
    return set()

def save_chats(chats_file, chats):
    chats_file.write_text(json.dumps(list(chats)))

def update_chats(session_manager, bot_token, chats_file):
    known_chats = load_chats(chats_file)
    api_url = f"https://api.telegram.org/bot{bot_token}"
    updates_url = api_url + "/getUpdates"
    try:
        resp = session_manager.get(updates_url)
        resp.raise_for_status()
        for update in resp.json().get("result", []):
            if "message" in update:
                known_chats.add(update["message"]["chat"]["id"])
            if "callback_query" in update:
                known_chats.add(update["callback_query"]["from"]["id"])
        if resp.json().get("result"):
            last_update_id = resp.json()["result"][-1]["update_id"]
            session_manager.get(f"{updates_url}?offset={last_update_id+1}")
    except Exception as e:
        logging.error(f"Error updating chats: {e}")
    save_chats(chats_file, known_chats)
    return known_chats

def fetch_offers(conn, table_name):
    cur = conn.cursor()
    cur.execute(f"SELECT id, token_address, sale_price, royalty_amount, fee_total FROM {table_name} WHERE sale_price IS NOT NULL")
    return cur.fetchall()

def calculate_floor_thresholds(offers):
    effective_prices = []
    for _, _, sale_price, _, fee_total in offers:
        effective_price = (sale_price or 0) + (fee_total or 0)
        effective_prices.append(effective_price)
    if len(effective_prices) < 2:
        return None, None
    effective_prices.sort()
    return effective_prices[0], effective_prices[1]

def send_notification(session_manager, bot_token, chat_id, message):
    api_url = f"https://api.telegram.org/bot{bot_token}"
    send_url = api_url + "/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": True
    }
    try:
        resp = session_manager.post(send_url, json=payload)
        if resp.status_code != 200:
            logging.warning(f"Failed to send to {chat_id}: {resp.text}")
    except Exception as e:
        logging.error(f"Error sending to {chat_id}: {e}")

def send_to_all_chats(session_manager, bot_token, chats, message):
    for chat_id in chats:
        send_notification(session_manager, bot_token, chat_id, message)

def main(cfg):
    db_path = Path("getgems_offers.db")
    table_name = "nft_offers"
    chats_file = Path("chats.json")
    bot_token = cfg["bot_token"]
    notify_interval = cfg.get("notify_interval_seconds", 60)
    floor_threshold_percent = cfg.get("floor_threshold_percent", 4)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )
    logger = logging.getLogger(__name__)
    if not db_path.exists():
        logger.error(f"Database not found: {db_path}")
        return
    session_manager = SessionManager(cfg)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    seen_offers = set()
    chats = update_chats(session_manager, bot_token, chats_file)
    startup_message = "🔔 GetGems Floor Alert Bot запущен и готов к работе!"
    send_to_all_chats(session_manager, bot_token, chats, startup_message)
    logger.info(f"Startup notification sent to {len(chats)} chats")
    try:
        while True:
            chats = update_chats(session_manager, bot_token, chats_file)
            offers = fetch_offers(conn, table_name)
            floor_price, second_price = calculate_floor_thresholds(offers)
            if floor_price is not None and second_price is not None:
                threshold_price = second_price * (1 - floor_threshold_percent / 100)
                for offer_id, token_address, sale_price, _, fee_total in offers:
                    effective_price = (sale_price or 0) + (fee_total or 0)
                    if offer_id not in seen_offers and effective_price <= threshold_price:
                        offer_url = f"https://getgems.io/collection/{cfg['collection_address']}/{token_address}?modalId=sale_info"
                        message = (
                            f"🔔 Floor gap alert:\n"
                            f"{offer_url}\n"
                            f"Effective: {effective_price:.4f} TON\n"
                            f"Floor: {floor_price:.4f} TON\n"
                            f"2nd: {second_price:.4f} TON\n"
                            f"Gap: {((second_price - effective_price) / second_price * 100):.1f}%"
                        )
                        send_to_all_chats(session_manager, bot_token, chats, message)
                        seen_offers.add(offer_id)
                        logger.info(f"Alert sent for offer {offer_id} at {effective_price:.4f} TON")
            time.sleep(notify_interval)
    except KeyboardInterrupt:
        logger.info("Shutting down notification service...")
        shutdown_message = "🔔 GetGems Floor Alert Bot завершает работу"
        send_to_all_chats(session_manager, bot_token, chats, shutdown_message)
        logger.info(f"Shutdown notification sent to {len(chats)} chats")
    finally:
        conn.close()

if __name__ == "__main__":
    from utils.config import load_config
    cfg = load_config("prod")
    main(cfg)
