#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
core/async_stream_parser.py

Асинхронный управляющий модуль: запускает бесконечный цикл парсинга через
run_cycle и выводит статистику и время выполнения запросов в лог.
"""

import argparse
import asyncio
import signal
import random
import contextlib
import time
from datetime import datetime

from utils.config import load_config
from utils.logging_cfg import setup_logger
from utils.statistics import Statistics
from utils.async_session import AsyncSession
from storage.db import (
    get_connection,
    init_tables,
    upsert_offer,
    close_connection,
)
from bs4 import BeautifulSoup
import json
import urllib.parse

def build_graphql_url(cfg: dict) -> str:
    query = json.dumps({
        "$and": [
            {"collectionAddress": cfg["collection_address"]},
            {"saleType": "fix_price"}
        ]
    }, separators=(",", ":"))
    sort = json.dumps([
        {"fixPrice": {"order": "asc"}},
        {"index":    {"order": "asc"}}
    ], separators=(",", ":"))
    variables = {"query": query, "attributes": None, "sort": sort, "count": cfg["count"]}
    extensions = {"persistedQuery": {"version": 1, "sha256Hash": cfg["sha256_hash"]}}
    ve = urllib.parse.quote(json.dumps(variables, separators=(",", ":")))
    ee = urllib.parse.quote(json.dumps(extensions, separators=(",", ":")))
    return f"{cfg['graphql_url']}?operationName=nftSearch&variables={ve}&extensions={ee}"

def parse_list_data(node: dict) -> dict:
    sale      = node.get("sale")     or {}
    max_offer = node.get("maxOffer") or {}
    stats     = node.get("stats")    or {}
    now = datetime.utcnow().isoformat()
    return {
        "token_address":     node.get("address"),
        "phone_number":      node.get("name"),
        "sale_contract":     sale.get("address"),
        "sale_price":        float(sale.get("fullPrice", 0))  / 1e9 if sale.get("fullPrice") else None,
        "sale_fee":          float(sale.get("networkFee", 0)) / 1e9 if sale.get("networkFee") else None,
        "max_offer_price":   float(max_offer.get("profitPrice", 0)) / 1e9 if max_offer.get("profitPrice") else None,
        "prev_owners_count": stats.get("prevOwnersCount"),
        "owner_address":     node.get("ownerAddress") or "",
        "updated_at":        now,
        "created_at":        now,
    }

async def fetch_offers_list(cfg: dict, session: AsyncSession, logger) -> list:
    url = build_graphql_url(cfg)
    headers = {
        "Accept":       "*/*",
        "Content-Type": "application/json",
        "x-gg-client":  cfg["x_gg_client"]
    }
    start = time.perf_counter()
    try:
        resp = await session.get(url, headers=headers)
        data = await resp.json()
        edges = data.get("data", {}).get("alphaNftItemSearch", {}).get("edges", [])
        elapsed = time.perf_counter() - start
        logger.info(f"fetch_offers_list: retrieved {len(edges)} edges in {elapsed:.2f}s")
        return edges
    except Exception as e:
        elapsed = time.perf_counter() - start
        logger.warning(f"fetch_offers_list error after {elapsed:.2f}s: {e}")
        return []

async def fetch_offer_details(cfg: dict, session: AsyncSession, token: str, logger) -> dict:
    url = f"https://getgems.io/collection/{cfg['collection_address']}/{token}?modalId=sale_info"
    await asyncio.sleep(random.uniform(cfg["request_delay_min"], cfg["request_delay_max"]))
    start = time.perf_counter()
    try:
        resp = await session.get(url)
        if resp.status != 200:
            elapsed = time.perf_counter() - start
            logger.warning(f"fetch_offer_details {token} status {resp.status} in {elapsed:.2f}s")
            return {}
        text = await resp.text()
        details = await asyncio.to_thread(_parse_details, text, logger, start, token)
        return details
    except Exception as e:
        elapsed = time.perf_counter() - start
        logger.warning(f"fetch_offer_details error for {token} after {elapsed:.2f}s: {e}")
        return {}

def _parse_details(html: str, logger, start: float, token: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        elapsed = time.perf_counter() - start
        logger.warning(f"_parse_details: no data for {token} after {elapsed:.2f}s")
        return {}
    gql = json.loads(script.string)
    cache = gql.get("props", {}).get("pageProps", {}).get("gqlCache", {})
    details = {}
    for k, v in cache.items():
        if k.startswith("NftSale"):
            details.update({
                "royalties_address": v.get("royaltyAddress"),
                "royalty_amount":    float(v.get("royaltyAmount", 0))  / 1e9 if v.get("royaltyAmount") else None,
                "fee_total":         float(v.get("marketplaceFee", 0)) / 1e9 if v.get("marketplaceFee") else None,
                "sale_type":         v.get("__typename"),
            })
        if k.startswith("NftItem") and "nft_address" not in details:
            details["nft_address"] = v.get("address")
    elapsed = time.perf_counter() - start
    logger.info(f"_parse_details for {token} in {elapsed:.2f}s")
    return details

class AsyncStreamParser:
    def __init__(self, cfg):
        self.cfg = cfg
        self.logger = setup_logger("async_stream_parser", cfg["log_level"])
        self.statistics = Statistics()
        self.cycle_count = 0
        self.running = True
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._signal_handler)

    def _signal_handler(self, sig, frame):
        self.logger.info(f"Signal {sig} received, shutting down parser")
        self.running = False

    def _calculate_cycle_delay(self) -> float:
        base = self.cfg["cycle_interval"]
        rnd = self.cfg.get("cycle_randomization", 0.0)
        return base + random.uniform(0, base * rnd)

    async def run_cycle(self, session: AsyncSession) -> int:
        logger = self.logger
        edges = await fetch_offers_list(self.cfg, session, logger)
        if not edges:
            return 0

        conn = await get_connection()
        await init_tables(conn)

        sem = asyncio.Semaphore(self.cfg["threads"])
        tasks = []
        for edge in edges:
            node = edge.get("node", {})
            tasks.append(asyncio.create_task(self._process_node(node, session, sem, logger, conn)))

        processed = 0
        for coro in asyncio.as_completed(tasks):
            try:
                await coro
                processed += 1
            except Exception:
                pass
        await close_connection(conn)
        return processed

    async def _process_node(self, node, session, sem, logger, conn):
        async with sem:
            ld = parse_list_data(node)
            details = await fetch_offer_details(self.cfg, session, node.get("address"), logger)
            rec = {**ld, **details}
            await upsert_offer(conn, rec)
            logger.info(f"Upserted {rec.get('token_address')}")

    async def print_stats(self):
        stats = self.statistics.get_stats()
        self.logger.info("=== STATISTICS ===")
        self.logger.info(f"Cycles: {stats['cycles_completed']}")
        self.logger.info(f"Offers total: {stats['total_offers_processed']}")
        self.logger.info(f"Errors: {stats['total_errors']}")
        self.logger.info(f"Avg cycle time: {stats['avg_cycle_time']:.2f}s")
        self.logger.info("==================")

    async def run(self):
        self.logger.info("Starting async parser")
        session = AsyncSession()

        # Запуск периодического будильника для корректного Ctrl+C
        asyncio.create_task(self._wakeup())

        while self.running:
            self.cycle_count += 1
            start_cycle = time.perf_counter()
            self.logger.info(f"Cycle #{self.cycle_count} start")
            try:
                count = await self.run_cycle(session)
                cycle_time = time.perf_counter() - start_cycle
                self.statistics.increment_cycle()
                self.statistics.add_offers(count)
                self.logger.info(f"Cycle #{self.cycle_count} done: {count} offers in {cycle_time:.2f}s")
            except Exception as e:
                self.statistics.add_error()
                self.logger.error(f"Error in cycle: {e}")
            if self.statistics.should_print_stats(self.cfg["stats_interval"]):
                await self.print_stats()
            await asyncio.sleep(self._calculate_cycle_delay())

        await session.close()
        self.logger.info("Async parser shutdown complete")

    async def _wakeup(self):
        while True:
            await asyncio.sleep(1)

if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Async Stream Parser")
    p.add_argument("--profile", choices=["dev", "prod"], default="dev")
    args = p.parse_args()
    cfg = load_config(args.profile)
    try:
        asyncio.run(AsyncStreamParser(cfg).run())
    except KeyboardInterrupt:
        pass
