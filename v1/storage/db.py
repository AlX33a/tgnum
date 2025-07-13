import sqlite3

def get_connection(path: str = "getgems_offers.db") -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    return conn

def init_tables(conn):
    cur = conn.cursor()
    # Создание основной таблицы с офферами
    cur.execute("""
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
    cur.execute("CREATE INDEX IF NOT EXISTS idx_token_address ON nft_offers(token_address)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_updated_at ON nft_offers(updated_at)")
    conn.commit()
