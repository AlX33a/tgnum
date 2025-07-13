#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
detail_parser.py

Скрипт для получения детальной информации по каждому офферу
из таблицы nft_offers без использования Selenium.
Результаты сохраняются в отдельную таблицу nft_offer_details.
"""

import json
import logging
import sqlite3
import time
from datetime import datetime

import requests
from bs4 import BeautifulSoup

# Константы
DB_PATH = "getgems_offers.db"
DETAILS_TABLE = "nft_offer_details"
COLLECTION_ADDRESS = "EQAOQdwdw8kGftJCSFgOErM1mBjYPe4DBPq8-AhF6vr9si5N"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36"
)


def setup_logger(name: str) -> logging.Logger:
    """
    Настройка логгера с выводом в файл и на консоль.
    Лог-файл имеет имя вида <name>_YYYYMMDD.log
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
    file_name = f"{name}_{datetime.now():%Y%m%d}.log"
    fh = logging.FileHandler(file_name, encoding="utf-8")
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)

    logger.handlers.clear()
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger


def connect_db(path: str = DB_PATH) -> sqlite3.Connection:
    """
    Подключение к SQLite и создание таблицы деталей, если не существует.
    :param path: путь к файлу БД
    :return: объект соединения
    """
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {DETAILS_TABLE} (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            offer_id INTEGER NOT NULL,
            sale_contract TEXT,
            owner_address TEXT,
            royalties_address TEXT,
            royalty_amount REAL,
            fee_total REAL,
            full_price REAL,
            currency TEXT,
            sale_type TEXT,
            nft_address TEXT,
            fetched_at TEXT,
            FOREIGN KEY(offer_id) REFERENCES nft_offers(id)
        )
    """)
    conn.commit()
    return conn


def get_pending_offers(conn: sqlite3.Connection, logger: logging.Logger) -> list:
    """
    Получает список офферов из nft_offers, для которых еще нет деталей.
    :param conn: соединение с БД
    :param logger: объект логгера
    :return: список кортежей (offer_id, URL)
    """
    cur = conn.cursor()
    cur.execute(f"""
        SELECT id, token_address
        FROM nft_offers
        WHERE offer_url IS NOT NULL
          AND id NOT IN (SELECT offer_id FROM {DETAILS_TABLE})
    """)
    pending = []
    for offer_id, token in cur.fetchall():
        url = f"https://getgems.io/collection/{COLLECTION_ADDRESS}/{token}?modalId=sale_info"
        pending.append((offer_id, url))
        logger.debug(f"Запланирован оффер {offer_id}: {url}")
    return pending


def fetch_offer_details(url: str, logger: logging.Logger) -> dict:
    """
    Загружает страницу оффера и извлекает JSON из <script id="__NEXT_DATA__">.
    Парсит данные NftSale и первый встретившийся NftItem для адреса токена.
    :param url: URL страницы оффера
    :param logger: объект логгера
    :return: словарь с деталями продажи
    """
    headers = {"User-Agent": USER_AGENT, "Accept": "text/html"}
    logger.info(f"GET {url}")
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script:
        logger.warning("Скрипт __NEXT_DATA__ не найден")
        return {}

    gql_cache = json.loads(script.string).get("props", {}) \
                                   .get("pageProps", {}) \
                                   .get("gqlCache", {})

    nft_address = None
    details = {}
    for key, val in gql_cache.items():
        if key.startswith("NftItem") and nft_address is None:
            nft_address = val.get("address")
        if key.startswith("NftSale"):
            details = {
                "sale_contract": val.get("address"),
                "owner_address": val.get("nftOwnerAddress"),
                "royalties_address": val.get("royaltyAddress"),
                "royalty_amount": float(val["royaltyAmount"]) / 1e9 if val.get("royaltyAmount") else None,
                "fee_total": float(val["marketplaceFee"]) / 1e9 if val.get("marketplaceFee") else None,
                "full_price": float(val["fullPrice"]) / 1e9 if val.get("fullPrice") else None,
                "currency": val.get("currency"),
                "sale_type": val.get("__typename"),
                "nft_address": nft_address
            }
            logger.debug(f"Найден NftSale: {list(val.keys())}")
            break

    logger.info(f"Детали оффера: {details}")
    return details


def save_offer_details(conn: sqlite3.Connection, offer_id: int, details: dict, logger: logging.Logger) -> None:
    """
    Сохраняет извлеченные детали оффера в БД.
    :param conn: соединение с БД
    :param offer_id: идентификатор оффера
    :param details: словарь с полями деталей
    :param logger: объект логгера
    """
    cur = conn.cursor()
    cur.execute(f"""
        INSERT INTO {DETAILS_TABLE} (
            offer_id, sale_contract, owner_address, royalties_address,
            royalty_amount, fee_total, full_price, currency,
            sale_type, nft_address, fetched_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        offer_id,
        details.get("sale_contract"),
        details.get("owner_address"),
        details.get("royalties_address"),
        details.get("royalty_amount"),
        details.get("fee_total"),
        details.get("full_price"),
        details.get("currency"),
        details.get("sale_type"),
        details.get("nft_address"),
        datetime.utcnow().isoformat()
    ))
    conn.commit()
    logger.info(f"Сохранены детали оффера {offer_id}")


def main():
    logger = setup_logger("detail_parser")
    logger.info("Старт парсинга деталей офферов")
    conn = connect_db()

    try:
        pending = get_pending_offers(conn, logger)
        logger.info(f"Офферов без деталей: {len(pending)}")
        for idx, (offer_id, url) in enumerate(pending, 1):
            logger.info(f"[{idx}/{len(pending)}] Обработка оффера {offer_id}")
            details = fetch_offer_details(url, logger)
            if details:
                save_offer_details(conn, offer_id, details, logger)
            else:
                logger.warning(f"Нет данных для оффера {offer_id}")
            time.sleep(1)  # пауза между запросами
    except Exception as e:
        logger.exception("Ошибка в процессе парсинга деталей: %s", e)
    finally:
        conn.close()
        logger.info("Парсинг деталей завершён")


if __name__ == "__main__":
    main()
