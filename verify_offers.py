#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_offers.py

Объединение raw→decode и запись в новую таблицу.
Поле full_price_tons обрезается до двух знаков после запятой.
Добавлено расширенное логирование dRPC-запросов и ответов для диагностики ошибок.
"""
import base64
import json
import logging
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import requests
from pytoniq_core.boc import Cell

DB_PATH     = Path("getgems_offers.db")
NEW_TABLE   = "nft_offers_verified"
DRPC_URL    = "https://ton.drpc.org/rest/runGetMethod"
DRPC_API_KEY= "AmsdWheF-UBCtl5AVBUjHj3-zqR-VUQR8JShrqRhf0qE"
LOG_FILE    = Path("verify_offers.log")

def setup_logging() -> None:
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, encoding="utf-8"),
        ],
    )

def run_get_method(address: str, method: str="get_sale_data", stack: List=None) -> Dict:
    stack = stack or []
    payload = {"address": address, "method": method, "stack": stack}
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "x-api-key": DRPC_API_KEY,
    }
    logging.debug("→ dRPC REQUEST: %s %s", method, address)
    logging.debug("Payload: %s", json.dumps(payload, ensure_ascii=False))
    try:
        resp = requests.post(DRPC_URL, json=payload, headers=headers, timeout=30)
        logging.debug("← HTTP %s", resp.status_code)
        resp.raise_for_status()
    except requests.RequestException as e:
        logging.error("!!! HTTP error for %s: %s", address, e, exc_info=True)
        raise
    try:
        data = resp.json()
        logging.debug("← dRPC RESPONSE JSON: %s", json.dumps(data, ensure_ascii=False))
    except ValueError:
        logging.error("!!! Invalid JSON response for %s: %s", address, resp.text[:500], exc_info=True)
        raise
    return data

def _hex_to_int(h: str) -> int:
    return int(h, 16)

def _extract_cell_payload(item):
    if isinstance(item, list) and item[0]=="cell":
        return item[1]
    if isinstance(item, dict):
        return item
    raise ValueError(f"Bad cell_item: {item!r}")

def _get_boc_base64(payload: dict) -> str:
    if "bytes" in payload:
        return payload["bytes"]
    obj = payload.get("object",{}).get("data",{})
    if "b64" in obj:
        return obj["b64"]
    raise ValueError(f"No BOC in payload: {payload!r}")

def _decode_address_cell(item) -> str:
    p = _extract_cell_payload(item)
    b64 = _get_boc_base64(p)
    cell = Cell.one_from_boc(base64.b64decode(b64))
    return cell.begin_parse().load_address().to_str()

def decode_sale_data(raw: dict) -> Dict:
    result = raw.get("result",{})
    stack  = result.get("stack",[])
    if not stack:
        raise ValueError("Empty stack")
    # базовые поля
    sale_type = bytes.fromhex(stack[0][1][2:]).decode("ascii",errors="ignore")
    is_complete= bool(_hex_to_int(stack[1][1]))
    created   = _hex_to_int(stack[2][1])
    created_at= datetime.fromtimestamp(created, tz=timezone.utc).isoformat()
    mp         = _decode_address_cell(stack[3])
    nft        = _decode_address_cell(stack[4])
    owner      = _decode_address_cell(stack[5])
    # full_price – отрезаем хвост
    raw_price  = _hex_to_int(stack[6][1]) / 1e9
    s = f"{raw_price:.10f}"
    intp,_,frac = s.partition('.')
    fp = float(f"{intp}.{frac[:2]}")
    fee        = _hex_to_int(stack[8][1]) / 1e9
    royalty    = _hex_to_int(stack[10][1]) / 1e9
    return {
        "sale_type": sale_type,
        "is_complete": is_complete,
        "created_at": created_at,
        "marketplace_address": mp,
        "nft_address": nft,
        "nft_owner_address": owner,
        "full_price_tons": fp,
        "market_fee_tons": fee,
        "royalty_amount_tons": royalty,
    }

def ensure_new_table(conn: sqlite3.Connection) -> None:
    cur=conn.cursor()
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS {NEW_TABLE} AS
    SELECT *,NULL AS sale_type,NULL AS is_complete,
           NULL AS created_at,NULL AS marketplace_address,
           NULL AS nft_address,NULL AS nft_owner_address,
           NULL AS full_price_tons,NULL AS market_fee_tons,
           NULL AS royalty_amount_tons,NULL AS verify,
           NULL AS description_error,NULL AS processed_at
    FROM nft_offers WHERE 0
    """)
    conn.commit()

def compare_fields(old: sqlite3.Row, dec: Dict)->(bool,str):
    errs=[]
    p_old=old["price_numeric"]
    if p_old is not None and abs(p_old-dec["full_price_tons"])>1e-6:
        errs.append(f"price_numeric({p_old})≠full_price({dec['full_price_tons']})")
    o_old=old["owner_address"]
    if o_old and o_old!=dec["nft_owner_address"]:
        errs.append(f"owner_address({o_old})≠nft_owner({dec['nft_owner_address']})")
    r_old=old["royalty_amount"]
    if r_old is not None and abs(r_old-dec["royalty_amount_tons"])>1e-6:
        errs.append(f"royalty_amount({r_old})≠royalty({dec['royalty_amount_tons']})")
    ok=len(errs)==0
    return ok, "; ".join(errs)

def upsert_verified(conn, old, dec, ok, desc):
    cur=conn.cursor()
    row=dict(old)
    row.update(dec)
    row.update({
        "verify": int(ok),
        "description_error": desc or None,
        "processed_at": datetime.utcnow().isoformat()
    })
    cols=", ".join(row.keys()); ph=", ".join("?"*len(row))
    cur.execute(f"INSERT INTO {NEW_TABLE} ({cols}) VALUES ({ph})", list(row.values()))
    conn.commit()

def main():
    setup_logging()
    if not DB_PATH.exists():
        logging.error("DB not found: %s", DB_PATH); sys.exit(1)
    conn=sqlite3.connect(DB_PATH)
    conn.row_factory=sqlite3.Row
    ensure_new_table(conn)
    cur=conn.cursor()
    cur.execute("SELECT * FROM nft_offers WHERE sale_contract IS NOT NULL")
    offers=cur.fetchall()
    logging.info("Всего оферов: %d", len(offers))
    for i,row in enumerate(offers,1):
        addr=row["sale_contract"]
        logging.info("[%d/%d] %s", i, len(offers), addr)
        try:
            raw=run_get_method(addr)
            ok_rpc = raw.get("ok",False) and raw.get("result",{}).get("exit_code",1)==0
            if not ok_rpc:
                logging.error("dRPC returned error payload for %s: %s", addr, raw)
                raise RuntimeError("dRPC payload error")
            dec=decode_sale_data(raw)
            ok,desc=compare_fields(row,dec)
            upsert_verified(conn,row,dec,ok,desc)
            logging.info("verify=%d", int(ok))
        except Exception as e:
            logging.exception("FATAL error for %s", addr)
            upsert_verified(conn,row,{},False,str(e))
        time.sleep(0.5)
    conn.close()
    logging.info("Done")

if __name__=="__main__":
    main()
