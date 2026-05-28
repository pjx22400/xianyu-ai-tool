"""数据库操作 — SQLite 持久化（连接池单例）"""
import json
import aiosqlite
from pathlib import Path
from typing import Optional
from src.config import config
from src.models import MonitorKeyword, XianyuItem


DB_PATH = str(config.DATA_DIR / "xianyu.db")
_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """获取数据库连接（单例复用，全模块共享）"""
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
    return _db


async def close_db():
    """关闭数据库连接（服务停止时调用）"""
    global _db
    if _db:
        await _db.close()
        _db = None


async def init_db():
    """初始化数据库表"""
    config.ensure_dirs()
    db = await get_db()
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            keyword TEXT NOT NULL UNIQUE,
            min_price REAL,
            max_price REAL,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT NOT NULL,
            keyword TEXT NOT NULL,
            title TEXT,
            price REAL,
            old_price REAL,
            seller TEXT DEFAULT '',
            location TEXT DEFAULT '',
            image_url TEXT DEFAULT '',
            item_url TEXT DEFAULT '',
            first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_new INTEGER DEFAULT 0,
            price_dropped INTEGER DEFAULT 0,
            price_drop_amount REAL DEFAULT 0,
            raw_data TEXT DEFAULT '{}',
            PRIMARY KEY (item_id, keyword)
        );

        CREATE INDEX IF NOT EXISTS idx_items_keyword ON items(keyword);
        CREATE INDEX IF NOT EXISTS idx_items_last_seen ON items(last_seen);

        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_title TEXT NOT NULL,
            cost_price REAL DEFAULT 0,
            sell_price REAL NOT NULL,
            shipping_cost REAL DEFAULT 0,
            platform_fee REAL DEFAULT 0,
            profit REAL GENERATED ALWAYS AS (sell_price - cost_price - shipping_cost - platform_fee) STORED,
            deal_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            notes TEXT DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_deals_date ON deals(deal_date);
    """)
    await db.commit()


# --- 关键词 CRUD ---

async def add_keyword(kw: MonitorKeyword) -> int:
    db = await get_db()
    cursor = await db.execute(
        "INSERT OR IGNORE INTO keywords (keyword, min_price, max_price) VALUES (?, ?, ?)",
        (kw.keyword, kw.min_price, kw.max_price),
    )
    await db.commit()
    return cursor.lastrowid


async def get_keywords(enabled_only: bool = True) -> list[MonitorKeyword]:
    db = await get_db()
    sql = "SELECT * FROM keywords"
    if enabled_only:
        sql += " WHERE enabled = 1"
    sql += " ORDER BY created_at DESC"
    rows = await db.execute_fetchall(sql)
    return [MonitorKeyword(**dict(r)) for r in rows]


async def delete_keyword(keyword: str) -> bool:
    db = await get_db()
    await db.execute("DELETE FROM keywords WHERE keyword = ?", (keyword,))
    await db.execute("DELETE FROM items WHERE keyword = ?", (keyword,))
    await db.commit()
    return True


async def toggle_keyword(keyword: str, enabled: bool):
    db = await get_db()
    await db.execute("UPDATE keywords SET enabled = ? WHERE keyword = ?", (int(enabled), keyword))
    await db.commit()


# --- 商品 CRUD ---

async def upsert_items(keyword: str, items: list[XianyuItem]):
    """批量更新/插入商品，并标记新商品和降价"""
    db = await get_db()
    for item in items:
        row = await db.execute_fetchall(
            "SELECT price, first_seen FROM items WHERE item_id = ? AND keyword = ?",
            (item.item_id, keyword),
        )
        if row:
            old_price = row[0]["price"]
            item.first_seen = row[0]["first_seen"]
            item.is_new = False
            if old_price > 0 and item.price < old_price * 0.99:
                item.price_dropped = True
                item.price_drop_amount = round(old_price - item.price, 2)
                item.old_price = old_price
            else:
                item.old_price = old_price
        else:
            item.is_new = True
            item.price_dropped = False

        await db.execute(
            """INSERT OR REPLACE INTO items
               (item_id, keyword, title, price, old_price, seller, location,
                image_url, item_url, first_seen, last_seen, is_new,
                price_dropped, price_drop_amount)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP),
                       CURRENT_TIMESTAMP, ?, ?, ?)""",
            (
                item.item_id, keyword, item.title, item.price, item.old_price,
                item.seller, item.location, item.image_url, item.item_url,
                item.first_seen, int(item.is_new), int(item.price_dropped),
                item.price_drop_amount,
            ),
        )
    await db.commit()


async def get_items(keyword: str, limit: int = 50) -> list[XianyuItem]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM items WHERE keyword = ? ORDER BY last_seen DESC LIMIT ?",
        (keyword, limit),
    )
    return [XianyuItem(**dict(r)) for r in rows]


async def get_latest_scan(keyword: str) -> Optional[str]:
    """获取某关键词的最后扫描时间"""
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT MAX(last_seen) as ts FROM items WHERE keyword = ?",
        (keyword,),
    )
    return row[0]["ts"] if row and row[0]["ts"] else None


# --- 利润追踪 CRUD ---

async def add_deal(item_title: str, sell_price: float, cost_price: float = 0,
                   shipping_cost: float = 0, platform_fee: float = 0,
                   notes: str = "") -> int:
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO deals (item_title, cost_price, sell_price, shipping_cost, platform_fee, notes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (item_title, cost_price, sell_price, shipping_cost, platform_fee, notes),
    )
    await db.commit()
    return cursor.lastrowid


async def get_deals(limit: int = 50) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM deals ORDER BY deal_date DESC LIMIT ?", (limit,)
    )
    return [dict(r) for r in rows]


async def get_profit_summary() -> dict:
    """利润汇总"""
    db = await get_db()
    row = await db.execute_fetchall("""
        SELECT
            COUNT(*) as total_deals,
            COALESCE(SUM(sell_price), 0) as total_revenue,
            COALESCE(SUM(cost_price), 0) as total_cost,
            COALESCE(SUM(shipping_cost), 0) as total_shipping,
            COALESCE(SUM(platform_fee), 0) as total_fee,
            COALESCE(SUM(profit), 0) as total_profit
        FROM deals
    """)
    d = dict(row[0]) if row else {}
    d["profit_margin"] = round((d.get("total_profit", 0) / d.get("total_revenue", 1)) * 100, 1) if d.get("total_revenue") else 0
    return d
