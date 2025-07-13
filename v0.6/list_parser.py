#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
list_parser_graphql.py

Скрипт для сбора списка офферов коллекции GetGems через GraphQL API.
Сохраняет данные в SQLite3 и логирует процесс.
"""

import json
import logging
import random
import sqlite3
import time
import urllib.parse
from datetime import datetime

import requests

# Константы
GRAPHQL_URL = "https://getgems.io/graphql/"
COLLECTION_ADDRESS = "EQAOQdwdw8kGftJCSFgOErM1mBjYPe4DBPq8-AhF6vr9si5N"
COUNT = 4
SHA256_HASH = "99377ac921442804742bd8a4d84047fbfbcf6dbca52879dc9c6e9029f5912b7b"
X_GG_CLIENT = "v:1 l:ru"
DB_PATH = "getgems_offers.db"

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/138.0.0.0 Safari/537.36"
]


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
    Устанавливает соединение с SQLite и создает таблицу, если она отсутствует.
    :param path: путь к файлу БД
    :return: объект соединения
    """
    conn = sqlite3.connect(path)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS nft_offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT,
            token_address TEXT,
            collection_name TEXT,
            collection_type TEXT,
            sale_contract TEXT,
            sale_price REAL,
            sale_fee REAL,
            sale_currency TEXT,
            max_offer_price REAL,
            prev_owners_count INTEGER,
            last_sale_price REAL,
            last_sale_date TEXT,
            owner_address TEXT,
            offer_url TEXT,
            created_at TEXT
        )
    """)
    conn.commit()
    return conn


def build_graphql_url(address: str, count: int, sha256: str) -> str:
    """
    Формирует URL для GraphQL-запроса с параметрами фильтрации и пагинации.
    :param address: адрес коллекции
    :param count: число записей за запрос
    :param sha256: хэш сохраненного GraphQL-запроса
    :return: готовый URL с query string
    """
    query = json.dumps({"$and": [
        {"collectionAddress": address},
        {"saleType": "fix_price"}
    ]}, separators=(",", ":"))
    sort = json.dumps([{"fixPrice": {"order": "asc"}}, {"index": {"order": "asc"}}],
                      separators=(",", ":"))
    variables = {"query": query, "attributes": None, "sort": sort, "count": count}
    extensions = {"persistedQuery": {"version": 1, "sha256Hash": sha256}}

    vars_enc = urllib.parse.quote(json.dumps(variables, separators=(",", ":")))
    ext_enc = urllib.parse.quote(json.dumps(extensions, separators=(",", ":")))
    return f"{GRAPHQL_URL}?operationName=nftSearch&variables={vars_enc}&extensions={ext_enc}"


def fetch_offers(logger: logging.Logger) -> list:
    """
    Выполняет HTTP-запрос к GraphQL API и парсит ответ в список офферов.
    :param logger: объект логгера для вывода статуса
    :return: список словарей с данными офферов
    """
    url = build_graphql_url(COLLECTION_ADDRESS, COUNT, SHA256_HASH)
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "x-gg-client": X_GG_CLIENT,
        "User-Agent": random.choice(USER_AGENTS)
    }
    logger.debug(f"Запрос: {url}")
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    edges = data.get("data", {}).get("alphaNftItemSearch", {}).get("edges", [])
    logger.info(f"Получено офферов: {len(edges)}")

    offers = []
    for edge in edges:
        node = edge.get("node", {})
        sale = node.get("sale", {})
        max_offer = node.get("maxOffer") or {}
        stats = node.get("stats") or {}
        last = node.get("lastSale") or {}

        offers.append({
            "phone_number": node.get("name"),
            "token_address": node.get("address"),
            "collection_name": node.get("collection", {}).get("name"),
            "collection_type": node.get("collection", {}).get("type"),
            "sale_contract": sale.get("address"),
            "sale_price": float(sale.get("fullPrice", 0)) / 1e9 if sale.get("fullPrice") else None,
            "sale_fee": float(sale.get("networkFee", 0)) / 1e9 if sale.get("networkFee") else None,
            "sale_currency": sale.get("currency"),
            "max_offer_price": float(max_offer.get("profitPrice", 0)) / 1e9 if max_offer.get("profitPrice") else None,
            "prev_owners_count": stats.get("prevOwnersCount"),
            "last_sale_price": float(last.get("fullPrice", 0)) / 1e9 if last.get("fullPrice") else None,
            "last_sale_date": datetime.utcfromtimestamp(last.get("date")).isoformat() if last.get("date") else None,
            "owner_address": node.get("ownerAddress") or "",
            "offer_url": f"https://getgems.io/token/{COLLECTION_ADDRESS}/{node.get('index')}",
            "created_at": datetime.utcnow().isoformat()
        })
    return offers


def save_offers(conn: sqlite3.Connection, logger: logging.Logger, offers: list) -> None:
    """
    Сохраняет список офферов в БД.
    :param conn: соединение с БД
    :param logger: объект логгера
    :param offers: список словарей с данными офферов
    """
    cur = conn.cursor()
    for o in offers:
        cur.execute("""
            INSERT INTO nft_offers (
                phone_number, token_address, collection_name, collection_type,
                sale_contract, sale_price, sale_fee, sale_currency,
                max_offer_price, prev_owners_count,
                last_sale_price, last_sale_date,
                owner_address, offer_url, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            o["phone_number"], o["token_address"], o["collection_name"], o["collection_type"],
            o["sale_contract"], o["sale_price"], o["sale_fee"], o["sale_currency"],
            o["max_offer_price"], o["prev_owners_count"],
            o["last_sale_price"], o["last_sale_date"],
            o["owner_address"], o["offer_url"], o["created_at"]
        ))
    conn.commit()
    logger.info(f"Сохранено офферов: {len(offers)}")


def main():
    logger = setup_logger("list_parser_graphql")
    logger.info("Старт парсинга списка офферов через GraphQL")
    conn = connect_db()
    try:
        offers = fetch_offers(logger)
        if offers:
            save_offers(conn, logger, offers)
        else:
            logger.warning("Нет новых офферов для сохранения")
    except Exception as e:
        logger.exception("Ошибка при сборе офферов: %s", e)
    finally:
        conn.close()
        logger.info("Парсинг списка завершён")


if __name__ == "__main__":
    main()
