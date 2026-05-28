"""数据库操作 — SQLite 持久化"""
import json
import aiosqlite
from pathlib import Path
from typing import Optional
from src.config import config
from src.models import MonitorKeyword, XianyuItem


DB_PATH = str(config.DATA_DIR / "xianyu.db")


async def get_db() -> aiosqlite.Connection:
    """获取数据库连接"""
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await db.execute("PRAGMA journal_mode=WAL")
    return db


async def init_db():
    """初始化数据库表"""
    config.ensure_dirs()
    db = await get_db()
    try:
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
        """)
        await db.commit()
    finally:
        await db.close()


# --- 关键词 CRUD ---

async def add_keyword(kw: MonitorKeyword) -> int:
    db = await get_db()
    try:
        cursor = await db.execute(
            "INSERT OR IGNORE INTO keywords (keyword, min_price, max_price) VALUES (?, ?, ?)",
            (kw.keyword, kw.min_price, kw.max_price),
        )
        await db.commit()
        return cursor.lastrowid
    finally:
        await db.close()


async def get_keywords(enabled_only: bool = True) -> list[MonitorKeyword]:
    db = await get_db()
    try:
        sql = "SELECT * FROM keywords"
        if enabled_only:
            sql += " WHERE enabled = 1"
        sql += " ORDER BY created_at DESC"
        rows = await db.execute_fetchall(sql)
        return [MonitorKeyword(**dict(r)) for r in rows]
    finally:
        await db.close()


async def delete_keyword(keyword: str) -> bool:
    db = await get_db()
    try:
        await db.execute("DELETE FROM keywords WHERE keyword = ?", (keyword,))
        await db.execute("DELETE FROM items WHERE keyword = ?", (keyword,))
        await db.commit()
        return True
    finally:
        await db.close()


async def toggle_keyword(keyword: str, enabled: bool):
    db = await get_db()
    try:
        await db.execute("UPDATE keywords SET enabled = ? WHERE keyword = ?", (int(enabled), keyword))
        await db.commit()
    finally:
        await db.close()


# --- 商品 CRUD ---

async def upsert_items(keyword: str, items: list[XianyuItem]):
    """批量更新/插入商品，并标记新商品和降价"""
    db = await get_db()
    try:
        for item in items:
            # 查旧记录
            row = await db.execute_fetchall(
                "SELECT price, first_seen FROM items WHERE item_id = ? AND keyword = ?",
                (item.item_id, keyword),
            )
            if row:
                old_price = row[0]["price"]
                item.first_seen = row[0]["first_seen"]
                item.is_new = False
                # 检测降价（阈值：降 1% 以上才提醒）
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
    finally:
        await db.close()


async def get_items(keyword: str, limit: int = 50) -> list[XianyuItem]:
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            "SELECT * FROM items WHERE keyword = ? ORDER BY last_seen DESC LIMIT ?",
            (keyword, limit),
        )
        return [XianyuItem(**dict(r)) for r in rows]
    finally:
        await db.close()


async def get_latest_scan(keyword: str) -> Optional[str]:
    """获取某关键词的最后扫描时间"""
    db = await get_db()
    try:
        row = await db.execute_fetchall(
            "SELECT MAX(last_seen) as ts FROM items WHERE keyword = ?",
            (keyword,),
        )
        return row[0]["ts"] if row and row[0]["ts"] else None
    finally:
        await db.close()
