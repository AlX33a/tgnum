#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
notify_floor_alerts.py

Асинхронный нотификатор floor gap для Telegram.
Обработка сигналов через signal.signal, безопасная работа с БД и HTTP.
"""

import asyncio
import signal
import sys
import json
from pathlib import Path
from datetime import datetime

from utils.config import load_config
from utils.async_session import AsyncSession
import aiosqlite
from utils.logging_cfg import setup_logger
from storage.db import get_offers_for_notifications, get_connection, close_connection

cfg = load_config("prod")
DB_PATH = Path("getgems_offers.db")
CHATS_FILE = Path("chats.json")

# Параметры алертов
TRASH_COUNT    = cfg.get("trash_count", 5)
SUPER_FACTOR   = cfg.get("super_factor", 0.96)
HALF_FACTOR    = cfg.get("half_factor", 0.98)
NOTIFY_INTERVAL = cfg.get("notify_interval_seconds", 60)

logger = setup_logger("notify_floor_alerts", cfg["log_level"])
running = True

def _signal_handler(sig, frame):
    global running
    logger.info(f"Signal {sig} received, shutting down notifier")
    running = False

# Кроссплатформенная регистрация сигналов
signal.signal(signal.SIGINT, _signal_handler)
try:
    signal.signal(signal.SIGTERM, _signal_handler)
except AttributeError:
    pass  # Windows may not have SIGTERM

async def load_chats() -> set:
    if CHATS_FILE.exists():
        return set(json.loads(CHATS_FILE.read_text(encoding="utf-8")))
    return set()

async def save_chats(chats: set):
    CHATS_FILE.write_text(json.dumps(list(chats)), encoding="utf-8")

async def update_chats(session: AsyncSession) -> set:
    chats = await load_chats()
    url = f"https://api.telegram.org/bot{cfg['bot_token']}/getUpdates"
    try:
        resp = await session.get(url)
        data = await resp.json()
        for u in data.get("result", []):
            if "message" in u:
                chats.add(u["message"]["chat"]["id"])
            if "callback_query" in u:
                chats.add(u["callback_query"]["from"]["id"])
        if data.get("result"):
            last = data["result"][-1]["update_id"]
            await session.get(f"{url}?offset={last+1}")
    except Exception as e:
        logger.warning("getUpdates error: %s", e)
    await save_chats(chats)
    logger.info("Known chats: %d", len(chats))
    return chats

def compute_thresholds(prices: list[float]) -> tuple[float, float] | tuple[None, None]:
    if len(prices) < 2:
        return None, None
    return prices[0], prices[1]

def make_message(url: str, rec: dict, label: str) -> str:
    lines = [f"{label}\n{url}"]
    for k, v in rec.items():
        lines.append(f"{k}: {v}")
    return "\n".join(lines)

async def send_all(session: AsyncSession, chats: set, text: str):
    url = f"https://api.telegram.org/bot{cfg['bot_token']}/sendMessage"
    for cid in chats:
        try:
            await session.post(url, json={
                "chat_id": cid,
                "text": text,
                "disable_web_page_preview": True
            })
        except Exception as e:
            logger.error("Send error to %s: %s", cid, e)

async def notifier_loop():
    session = AsyncSession()
    db = await get_connection()
    # Чтение офферов для алертов
    seen_trash = set()
    seen_half  = set()
    seen_super = set()

    chats = await update_chats(session)
    if chats:
        await send_all(session, chats, "🔔 Notifier started")

    global running
    while running:
        try:
            chats = await update_chats(session)
            rows = await get_offers_for_notifications(db, TRASH_COUNT)
            effs = [p + f for _, p, f, _, _, _ in rows]
            floor, second = compute_thresholds(effs)

            for idx, (token, p, f, ramt, ftot, created) in enumerate(rows, start=1):
                eff = p + f
                url = (
                    f"https://getgems.io/collection/"
                    f"{cfg['collection_address']}/{token}?modalId=sale_info"
                )
                rec = {
                    "sale_price":       p,
                    "sale_fee":         f,
                    "royalty_amount":   ramt,
                    "fee_total":        ftot,
                    "created_at":       created
                }

                # Trash alert: новые в топ-N
                if token not in seen_trash:
                    label = f"🗑️ Trash Alert: new #{idx}"
                    await send_all(session, chats, make_message(url, rec, label))
                    seen_trash.add(token)

                # Half & Super alerts
                if floor is not None and second is not None:
                    half_thr  = floor * HALF_FACTOR
                    super_thr = floor * SUPER_FACTOR
                    if eff <= half_thr and token not in seen_half:
                        label = "⚠️ Half Alert (−2%)"
                        await send_all(session, chats, make_message(url, rec, label))
                        seen_half.add(token)
                    if eff <= super_thr and token not in seen_super:
                        label = "🔥 Super Alert (−4%)"
                        await send_all(session, chats, make_message(url, rec, label))
                        seen_super.add(token)

        except Exception as e:
            logger.exception("Notifier loop error: %s", e)

        await asyncio.sleep(NOTIFY_INTERVAL)

    await session.close()
    await close_connection(db)
    logger.info("Notifier shutdown complete")

def main():
    try:
        asyncio.run(notifier_loop())
    except KeyboardInterrupt:
        pass

if __name__ == "__main__":
    main()
