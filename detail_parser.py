#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
detail_parser.py

Дополнение данных из detail-страниц.
"""
import time
import sqlite3
import logging
import random
import json
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup

# Единственный User-Agent
USER_AGENTS = ["Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/123.0.0.0 Safari/537.36"]

def get_random_user_agent():
    return USER_AGENTS[0]

def setup_logging():
    logger = logging.getLogger('detail_parser')
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh = logging.FileHandler(f"detail_parser_{datetime.now():%Y%m%d}.log", encoding='utf-8')
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.handlers.clear()
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

class DetailParser:
    def __init__(self):
        self.logger = setup_logging()
        self.db = sqlite3.connect('getgems_offers.db')
        opts = Options()
        opts.add_argument('--headless')
        opts.add_argument('--no-sandbox')
        opts.add_argument('--disable-dev-shm-usage')
        opts.add_argument('--disable-gpu')
        opts.add_argument('--window-size=1920,1080')
        ua = get_random_user_agent()
        opts.add_argument(f'--user-agent={ua}')
        self.driver = webdriver.Chrome(options=opts)
        self.wait = WebDriverWait(self.driver, 10)
        self.logger.info(f"WebDriver инициализирован, UA: {ua}")

    def get_pending(self):
        cur = self.db.cursor()
        cur.execute("""
            SELECT id, offer_url
            FROM nft_offers
            WHERE (
                owner_address IS NULL OR
                sale_contract IS NULL OR
                royalties_address IS NULL OR
                royalty_amount IS NULL OR
                fee_total IS NULL
            ) AND offer_url IS NOT NULL
        """)
        rows = cur.fetchall()
        self.logger.info(f"Pending offers: {len(rows)}")
        return rows

    def parse_next_data(self, soup):
        tag = soup.find('script', id="__NEXT_DATA__")
        if not tag:
            return {}
        return json.loads(tag.string).get('props', {})\
                                .get('pageProps', {})\
                                .get('gqlCache', {})

    def extract(self, url):
        self.logger.info(f"Open {url}")
        self.driver.get(url)
        try:
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, 'script')))
        except TimeoutException:
            self.logger.error("Timeout waiting scripts")
        time.sleep(1)
        soup = BeautifulSoup(self.driver.page_source, 'html.parser')
        gql = self.parse_next_data(soup)

        sale_obj = None
        for key, val in gql.items():
            if key.startswith("NftSale"):
                sale_obj = val
                break

        data = {}
        if sale_obj:
            # Парсим «как есть»
            data = {
                'sale_contract': sale_obj.get('address'),
                'owner_address': sale_obj.get('nftOwnerAddress'),
                'royalties_address': sale_obj.get('royaltyAddress'),
                'royalty_amount': float(sale_obj.get('royaltyAmount') or 0) / 1e9,
                'fee_total': float(sale_obj.get('marketplaceFee') or 0) / 1e9
            }
            self.logger.info(f"Extracted: {data}")
        return data

    def update(self, offer_id, d):
        cur = self.db.cursor()
        cur.execute("""
            UPDATE nft_offers SET
                owner_address = ?,
                sale_contract = ?,
                royalties_address = ?,
                royalty_amount = ?,
                fee_total = ?
            WHERE id = ?
        """, (
            d.get('owner_address'),
            d.get('sale_contract'),
            d.get('royalties_address'),
            d.get('royalty_amount'),
            d.get('fee_total'),
            offer_id
        ))
        self.db.commit()
        self.logger.info(f"Updated ID={offer_id}")

    def run(self):
        pending = self.get_pending()
        for idx, (oid, url) in enumerate(pending, 1):
            self.logger.info(f"[{idx}/{len(pending)}] ID={oid}")
            details = self.extract(url)
            if details:
                self.update(oid, details)
            time.sleep(2)
        self.cleanup()
        self.logger.info("Готово")

    def cleanup(self):
        self.driver.quit()
        self.db.close()

if __name__ == "__main__":
    DetailParser().run()
