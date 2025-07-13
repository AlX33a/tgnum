#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import urllib.parse
import time
import sqlite3
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup

from utils.logging_cfg import setup_logger
from utils.session_manager import SessionManager
from storage.db import init_tables

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

def fetch_offers_list(cfg: dict, session_manager: SessionManager, logger) -> list:
    url = build_graphql_url(cfg)
    headers = {
        "Accept": "*/*",
        "Content-Type": "application/json",
        "x-gg-client": cfg["x_gg_client"]
    }
    logger.debug(f"GET GraphQL {url}")
    resp = session_manager.get(url, headers=headers)
    try:
        data = resp.json()
    except ValueError:
        logger.error("JSON decode error in fetch_offers_list")
        return []
    edges = data.get("data", {}).get("alphaNftItemSearch", {}).get("edges", [])
    logger.info(f"Получено офферов: {len(edges)}")
    return edges

def parse_list_data(node: dict) -> dict:
    sale = node.get("sale") or {}
    max_offer = node.get("maxOffer") or {}
    stats = node.get("stats") or {}
    last = node.get("lastSale") or {}
    return {
        "token_address": node.get("address"),
        "sale_price": float(sale.get("fullPrice", 0)) / 1e9 if sale.get("fullPrice") else None,
        "royalty_amount": float(v.get("royaltyAmount", 0)) / 1e9 if (v:=sale).get("royaltyAmount") else None,
        "fee_total": float(v.get("networkFee", 0)) / 1e9 if v.get("networkFee") else None,
        "created_at": datetime.utcnow().isoformat(),
        "updated_at": datetime.utcnow().isoformat()
    }

def fetch_offer_details(token: str, cfg: dict, session_manager: SessionManager, logger) -> dict:
    url = f"https://getgems.io/collection/{cfg['collection_address']}/{token}?modalId=sale_info"
    time.sleep(cfg.get("request_delay_min", 1.0))
    logger.debug(f"GET Details {url}")
    resp = session_manager.get(url)
    if resp.status_code != 200:
        logger.warning(f"Details {token} returned {resp.status_code}")
        return {}
    soup = BeautifulSoup(resp.text, "html.parser")
    script = soup.find("script", id="__NEXT_DATA__")
    if not script or not script.string:
        return {}
    raw = script.string
    try:
        gql = json.loads(raw)
    except ValueError:
        return {}
    cache = gql.get("props", {}).get("pageProps", {}).get("gqlCache", {})
    for k, v in cache.items():
        if k.startswith("NftSale"):
            return {
                "royalties_address": v.get("royaltyAddress"),
                "royalty_amount": float(v.get("royaltyAmount", 0)) / 1e9 if v.get("royaltyAmount") else None,
                "fee_total": float(v.get("marketplaceFee", 0)) / 1e9 if v.get("marketplaceFee") else None
            }
    return {}

def upsert_offer(conn: sqlite3.Connection, data: dict, logger):
    token = data.get("token_address")
    if not token:
        return
    cur = conn.cursor()
    cur.execute("SELECT created_at FROM nft_offers WHERE token_address=?", (token,))
    row = cur.fetchone()
    now = datetime.utcnow().isoformat()
    data["updated_at"] = now
    if row:
        data["created_at"] = row[0]
        fields = ", ".join(f"{k}=?" for k in data)
        vals = list(data.values()) + [token]
        cur.execute(f"UPDATE nft_offers SET {fields} WHERE token_address=?", vals)
    else:
        data["created_at"] = now
        cols = ", ".join(data.keys())
        placeholders = ", ".join("?" for _ in data)
        cur.execute(f"INSERT INTO nft_offers ({cols}) VALUES ({placeholders})", list(data.values()))
    conn.commit()

def run_stream_parser(cfg: dict, conn: sqlite3.Connection) -> int:
    logger = setup_logger("stream_parser", cfg["log_level"])
    init_tables(conn)
    session_manager = SessionManager(cfg)
    edges = fetch_offers_list(cfg, session_manager, logger)
    if not edges:
        logger.warning("Empty offers list")
        return 0
    processed = 0
    with ThreadPoolExecutor(max_workers=cfg["threads"]) as exe:
        futures = {
            exe.submit(lambda n: (parse_list_data(n), fetch_offer_details(n.get("address"), cfg, session_manager, logger)), edge.get("node", {})): edge.get("node", {}).get("address")
            for edge in edges
        }
        for fut in as_completed(futures):
            tok = futures[fut]
            try:
                ld, dd = fut.result()
                upsert_offer(conn, {**ld, **dd}, logger)
                processed += 1
                logger.info(f"Processed {tok} ({processed}/{len(edges)})")
            except Exception as e:
                logger.error(f"Error processing {tok}: {e}")
    return processed
