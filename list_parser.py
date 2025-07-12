#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
list_parser.py

Сбор списка офферов GetGems.
"""
import time
import sqlite3
import logging
import random
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
    logger = logging.getLogger('getgems_list_parser')
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    fh = logging.FileHandler(f'getgems_list_parser_{datetime.now().strftime("%Y%m%d")}.log', encoding='utf-8')
    fh.setFormatter(fmt)
    ch = logging.StreamHandler()
    ch.setFormatter(fmt)
    logger.handlers.clear()
    logger.addHandler(fh)
    logger.addHandler(ch)
    return logger

class GetGemsListParser:
    def __init__(self):
        self.logger = setup_logging()
        self.driver = None
        self.wait = None
        self.db = None

    def setup_database(self):
        self.db = sqlite3.connect('getgems_offers.db')
        cur = self.db.cursor()
        cur.execute('''
        CREATE TABLE IF NOT EXISTS nft_offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT NOT NULL,
            price_numeric REAL,
            currency TEXT,
            owner TEXT,
            owner_address TEXT,
            offer_url TEXT,
            sale_contract TEXT,
            royalties_address TEXT,
            royalty_amount REAL,
            fee_total REAL,
            created_at TEXT
        )
        ''')
        self.db.commit()
        self.logger.info("База данных настроена")

    def initialize_driver(self):
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
        # Отключаем флаг webdriver
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.logger.info(f"WebDriver инициализирован, UA: {ua}")

    def parse_price(self, text):
        t = text.replace('Buy Now', '').replace('TON', '').replace(',', '').strip()
        try:
            return float(t), 'TON'
        except:
            return None, None

    def extract_offers(self, url):
        offers = []
        try:
            self.logger.info(f"Загрузка: {url}")
            self.driver.get(url)
            self.wait.until(EC.presence_of_element_located((By.TAG_NAME, "table")))
            time.sleep(2)
            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
            rows = soup.select('table tr')[1:]
            for row in rows:
                cells = row.find_all('td')
                if len(cells) < 2:
                    continue
                phone = cells[0].get_text(strip=True)
                price_num, currency = self.parse_price(cells[1].get_text(strip=True))
                owner = cells[-1].get_text(strip=True)
                link_tag = cells[0].find('a')
                link = ("https://getgems.io" + link_tag['href']) if link_tag and link_tag.get('href') else None
                offers.append({
                    'phone_number': phone,
                    'price_numeric': price_num,
                    'currency': currency,
                    'owner': owner,
                    'owner_address': None,
                    'offer_url': link,
                    'sale_contract': None,
                    'royalties_address': None,
                    'royalty_amount': None,
                    'fee_total': None,
                    'created_at': datetime.now().isoformat()
                })
        except TimeoutException:
            self.logger.error("Таймаут загрузки")
        except Exception as e:
            self.logger.error(f"Ошибка парсинга: {e}")
        return offers

    def save_offers(self, offers):
        cur = self.db.cursor()
        for o in offers:
            cur.execute('''
                INSERT INTO nft_offers (
                    phone_number, price_numeric, currency,
                    owner, owner_address, offer_url, sale_contract,
                    royalties_address, royalty_amount, fee_total,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                o['phone_number'], o['price_numeric'], o['currency'],
                o['owner'], o['owner_address'], o['offer_url'], o['sale_contract'],
                o['royalties_address'], o['royalty_amount'], o['fee_total'],
                o['created_at']
            ))
        self.db.commit()
        self.logger.info(f"Сохранено {len(offers)} предложений")

    def run(self):
        self.logger.info("Старт парсинга списка предложений")
        self.setup_database()
        self.initialize_driver()
        base = "https://getgems.io/collection/EQAOQdwdw8kGftJCSFgOErM1mBjYPe4DBPq8-AhF6vr9si5N"
        filt = "?filter=%7B%22saleType%22%3A%22fix_price%22%7D"
        all_offers = []
        page = 1
        while len(all_offers) < 28:
            url = base + filt + (f"&page={page}" if page > 1 else "")
            offers = self.extract_offers(url)
            if not offers:
                break
            self.save_offers(offers)
            all_offers.extend(offers)
            if len(all_offers) >= 28:
                break
            page += 1
            time.sleep(3)
        self.cleanup()

    def cleanup(self):
        if self.driver:
            self.driver.quit()
        if self.db:
            self.db.close()
        self.logger.info("Готово")

if __name__ == "__main__":
    GetGemsListParser().run()
