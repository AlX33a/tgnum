#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
storage/db.py

Асинхронная работа с SQLite через aiosqlite с поддержкой WAL-режима
и защитой от блокировок при параллельном доступе.
"""

import aiosqlite
from datetime import datetime

async def get_connection(path: str = "getgems_offers.db") -> aiosqlite.Connection:
    """
    Асинхронное подключение к SQLite с настройкой WAL-режима и таймаутом.
    
    Args:
        path: Путь к файлу базы данных
        
    Returns:
        aiosqlite.Connection: Настроенное соединение с БД
    """
    # Увеличенный таймаут для предотвращения блокировок
    conn = await aiosqlite.connect(path, timeout=10.0)
    
    # Включаем WAL-режим для лучшей параллельности
    await conn.execute("PRAGMA journal_mode=WAL")
    
    # Оптимизация для параллельного доступа
    await conn.execute("PRAGMA synchronous=NORMAL")
    await conn.execute("PRAGMA cache_size=10000")
    await conn.execute("PRAGMA temp_store=MEMORY")
    
    await conn.commit()
    return conn

async def init_tables(conn: aiosqlite.Connection):
    """
    Создание таблиц в БД асинхронно.
    
    Args:
        conn: Соединение с базой данных
    """
    await conn.execute("""
      CREATE TABLE IF NOT EXISTS nft_offers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        token_address TEXT UNIQUE,
        phone_number TEXT,
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
        royalties_address TEXT,
        royalty_amount REAL,
        fee_total REAL,
        full_price REAL,
        currency TEXT,
        sale_type TEXT,
        nft_address TEXT,
        updated_at TEXT,
        created_at TEXT
      )
    """)
    
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_token_address ON nft_offers(token_address)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_updated_at ON nft_offers(updated_at)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_sale_price ON nft_offers(sale_price)")
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_created_at ON nft_offers(created_at)")
    
    await conn.commit()

async def upsert_offer(conn: aiosqlite.Connection, data: dict):
    """
    Асинхронная вставка или обновление оффера с минимальным временем блокировки.
    
    Args:
        conn: Соединение с базой данных
        data: Словарь с данными оффера
    """
    token = data.get("token_address")
    if not token:
        return

    now = datetime.utcnow().isoformat()
    data["updated_at"] = now

    try:
        # Начинаем транзакцию
        await conn.execute("BEGIN IMMEDIATE")
        
        # Проверяем существование записи
        cursor = await conn.execute(
            "SELECT created_at FROM nft_offers WHERE token_address = ?",
            (token,)
        )
        row = await cursor.fetchone()

        if row:
            # Обновляем существующую запись, сохраняя оригинальную created_at
            data["created_at"] = row[0]
            fields = list(data.keys())
            set_clause = ", ".join(f"{f}=?" for f in fields)
            values = [data[f] for f in fields] + [token]
            await conn.execute(
                f"UPDATE nft_offers SET {set_clause} WHERE token_address = ?",
                values
            )
        else:
            # Новая запись
            data["created_at"] = data.get("created_at", now)
            columns = ", ".join(data.keys())
            placeholders = ", ".join("?" for _ in data)
            await conn.execute(
                f"INSERT INTO nft_offers ({columns}) VALUES ({placeholders})",
                list(data.values())
            )

        # Коммитим транзакцию
        await conn.commit()
        
    except Exception as e:
        # Откатываем транзакцию в случае ошибки
        await conn.rollback()
        raise e

async def get_offers_for_notifications(conn: aiosqlite.Connection, limit: int = 5) -> list:
    """
    Получение офферов для нотификаций с минимальным временем блокировки.
    
    Args:
        conn: Соединение с базой данных
        limit: Количество записей для получения
        
    Returns:
        list: Список кортежей с данными офферов
    """
    sql = """
      SELECT token_address, sale_price, sale_fee, royalty_amount, fee_total, created_at
        FROM nft_offers
       WHERE sale_price IS NOT NULL
       ORDER BY (sale_price + sale_fee) ASC
       LIMIT ?
    """
    
    cursor = await conn.execute(sql, (limit,))
    return await cursor.fetchall()

async def close_connection(conn: aiosqlite.Connection):
    """
    Безопасное закрытие соединения с БД.
    
    Args:
        conn: Соединение с базой данных
    """
    if conn:
        await conn.close()
