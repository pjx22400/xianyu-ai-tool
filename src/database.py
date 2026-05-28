"""数据库操作 — SQLite 持久化 v0.5（多租户）

v0.5 SaaS: users + refresh_tokens + user_id 隔离
"""

import json
import uuid
import aiosqlite
from pathlib import Path
from typing import Optional
from src.config import config
from src.models import MonitorKeyword, XianyuItem

DB_PATH = str(config.DATA_DIR / "xianyu.db")
_db: aiosqlite.Connection | None = None
DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000000"  # 迁移用


async def get_db() -> aiosqlite.Connection:
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA journal_mode=WAL")
        await _db.execute("PRAGMA foreign_keys=ON")
    return _db


async def close_db():
    global _db
    if _db:
        await _db.close()
        _db = None


async def init_db():
    """初始化数据库表 + 向后兼容迁移"""
    config.ensure_dirs()
    db = await get_db()

    # v0.5: 新表
    await db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            tier TEXT DEFAULT 'free',
            tier_expires_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS refresh_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL REFERENCES users(id),
            token TEXT NOT NULL UNIQUE,
            expires_at TIMESTAMP NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_refresh_user ON refresh_tokens(user_id);
        CREATE INDEX IF NOT EXISTS idx_refresh_token ON refresh_tokens(token);

        CREATE TABLE IF NOT EXISTS keywords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL DEFAULT '""" + DEFAULT_USER_ID + """',
            keyword TEXT NOT NULL,
            min_price REAL,
            max_price REAL,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, keyword)
        );

        CREATE TABLE IF NOT EXISTS items (
            item_id TEXT NOT NULL,
            keyword TEXT NOT NULL,
            user_id TEXT NOT NULL DEFAULT '""" + DEFAULT_USER_ID + """',
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
            PRIMARY KEY (item_id, keyword, user_id)
        );

        CREATE INDEX IF NOT EXISTS idx_items_keyword ON items(keyword);
        CREATE INDEX IF NOT EXISTS idx_items_last_seen ON items(last_seen);
        CREATE INDEX IF NOT EXISTS idx_items_user ON items(user_id);

        CREATE TABLE IF NOT EXISTS deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL DEFAULT '""" + DEFAULT_USER_ID + """',
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
        CREATE INDEX IF NOT EXISTS idx_deals_user ON deals(user_id);

        CREATE TABLE IF NOT EXISTS accounts (
            account_id TEXT NOT NULL,
            user_id TEXT NOT NULL DEFAULT '""" + DEFAULT_USER_ID + """',
            name TEXT DEFAULT '',
            cookies TEXT DEFAULT '',
            is_default INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (account_id, user_id)
        );

        CREATE TABLE IF NOT EXISTS cs_messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL DEFAULT '""" + DEFAULT_USER_ID + """',
            chat_id TEXT NOT NULL,
            sender_name TEXT DEFAULT '',
            content TEXT NOT NULL,
            direction TEXT DEFAULT 'in',
            msg_time INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_cs_chat ON cs_messages(chat_id);
        CREATE INDEX IF NOT EXISTS idx_cs_time ON cs_messages(msg_time);
        CREATE INDEX IF NOT EXISTS idx_cs_user ON cs_messages(user_id);

        CREATE TABLE IF NOT EXISTS orders (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            plan TEXT NOT NULL DEFAULT 'pro_monthly',
            amount REAL NOT NULL,
            status TEXT DEFAULT 'pending',
            payment_method TEXT DEFAULT 'mock',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            paid_at TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_orders_user ON orders(user_id);
        CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);

        CREATE TABLE IF NOT EXISTS price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT NOT NULL DEFAULT '""" + DEFAULT_USER_ID + """',
            item_id TEXT NOT NULL,
            price REAL NOT NULL,
            recorded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_ph_item ON price_history(item_id);
        CREATE INDEX IF NOT EXISTS idx_ph_user ON price_history(user_id);

        CREATE TABLE IF NOT EXISTS email_configs (
            user_id TEXT PRIMARY KEY,
            smtp_host TEXT NOT NULL DEFAULT 'smtp.qq.com',
            smtp_port INTEGER NOT NULL DEFAULT 587,
            sender_email TEXT NOT NULL DEFAULT '',
            sender_password TEXT NOT NULL DEFAULT '',
            use_tls INTEGER NOT NULL DEFAULT 1,
            use_ssl INTEGER NOT NULL DEFAULT 0,
            notify_new_items INTEGER NOT NULL DEFAULT 1,
            notify_price_drops INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    await db.commit()


# ==================== 用户 CRUD ====================

async def create_user(email: str, password_hash: str, tier: str = "free") -> str:
    """创建用户，返回 user_id"""
    db = await get_db()
    uid = str(uuid.uuid4())
    await db.execute(
        "INSERT INTO users (id, email, password_hash, tier) VALUES (?, ?, ?, ?)",
        (uid, email, password_hash, tier),
    )
    await db.commit()
    return uid


async def get_user_by_email(email: str) -> Optional[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM users WHERE email = ?", (email,)
    )
    return dict(rows[0]) if rows else None


async def get_user_by_id(user_id: str) -> Optional[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM users WHERE id = ?", (user_id,)
    )
    return dict(rows[0]) if rows else None


async def get_all_users() -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT id, email, tier, tier_expires_at, created_at FROM users ORDER BY created_at DESC"
    )
    return [dict(r) for r in rows]


# ==================== Refresh Token ====================

async def save_refresh_token(user_id: str, token: str, expires_at: str):
    db = await get_db()
    await db.execute(
        "INSERT INTO refresh_tokens (user_id, token, expires_at) VALUES (?, ?, ?)",
        (user_id, token, expires_at),
    )
    await db.commit()


async def verify_refresh_token(token: str) -> Optional[str]:
    """验证 refresh token，返回 user_id"""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT user_id, expires_at FROM refresh_tokens WHERE token = ?", (token,)
    )
    if not rows:
        return None
    row = dict(rows[0])
    from datetime import datetime
    if datetime.fromisoformat(row["expires_at"]) < datetime.utcnow():
        await db.execute("DELETE FROM refresh_tokens WHERE token = ?", (token,))
        await db.commit()
        return None
    return row["user_id"]


async def revoke_refresh_token(token: str):
    db = await get_db()
    await db.execute("DELETE FROM refresh_tokens WHERE token = ?", (token,))
    await db.commit()


async def revoke_all_user_tokens(user_id: str):
    db = await get_db()
    await db.execute("DELETE FROM refresh_tokens WHERE user_id = ?", (user_id,))
    await db.commit()


# ==================== 关键词 CRUD ====================

async def add_keyword(kw: MonitorKeyword, user_id: str) -> int:
    db = await get_db()
    cursor = await db.execute(
        "INSERT OR IGNORE INTO keywords (user_id, keyword, min_price, max_price) VALUES (?, ?, ?, ?)",
        (user_id, kw.keyword, kw.min_price, kw.max_price),
    )
    await db.commit()
    return cursor.lastrowid


async def get_keywords(user_id: str, enabled_only: bool = True) -> list[MonitorKeyword]:
    db = await get_db()
    sql = "SELECT * FROM keywords WHERE user_id = ?"
    if enabled_only:
        sql += " AND enabled = 1"
    sql += " ORDER BY created_at DESC"
    rows = await db.execute_fetchall(sql, (user_id,))
    return [MonitorKeyword(**dict(r)) for r in rows]


async def count_keywords(user_id: str) -> int:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT COUNT(*) as c FROM keywords WHERE user_id = ?", (user_id,)
    )
    return rows[0]["c"] if rows else 0


async def delete_keyword(keyword: str, user_id: str) -> bool:
    db = await get_db()
    await db.execute("DELETE FROM keywords WHERE keyword = ? AND user_id = ?", (keyword, user_id))
    await db.execute("DELETE FROM items WHERE keyword = ? AND user_id = ?", (keyword, user_id))
    await db.commit()
    return True


async def toggle_keyword(keyword: str, enabled: bool, user_id: str):
    db = await get_db()
    await db.execute(
        "UPDATE keywords SET enabled = ? WHERE keyword = ? AND user_id = ?",
        (int(enabled), keyword, user_id),
    )
    await db.commit()


# ==================== 商品 CRUD ====================

async def upsert_items(keyword: str, items: list[XianyuItem], user_id: str):
    db = await get_db()
    for item in items:
        row = await db.execute_fetchall(
            "SELECT price, first_seen FROM items WHERE item_id = ? AND keyword = ? AND user_id = ?",
            (item.item_id, keyword, user_id),
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
               (item_id, keyword, user_id, title, price, old_price, seller, location,
                image_url, item_url, first_seen, last_seen, is_new,
                price_dropped, price_drop_amount)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP),
                       CURRENT_TIMESTAMP, ?, ?, ?)""",
            (
                item.item_id, keyword, user_id, item.title, item.price, item.old_price,
                item.seller, item.location, item.image_url, item.item_url,
                item.first_seen, int(item.is_new), int(item.price_dropped),
                item.price_drop_amount,
            ),
        )

        # 记录价格变化（已有商品且价格不同时）
        if not item.is_new and row and item.price != row[0]["price"]:
            await db.execute(
                "INSERT INTO price_history (user_id, item_id, price) VALUES (?, ?, ?)",
                (user_id, item.item_id, item.price),
            )

    await db.commit()


async def get_items(keyword: str, user_id: str, limit: int = 50) -> list[XianyuItem]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM items WHERE keyword = ? AND user_id = ? ORDER BY last_seen DESC LIMIT ?",
        (keyword, user_id, limit),
    )
    return [XianyuItem(**dict(r)) for r in rows]


async def get_latest_scan(keyword: str, user_id: str) -> Optional[str]:
    db = await get_db()
    row = await db.execute_fetchall(
        "SELECT MAX(last_seen) as ts FROM items WHERE keyword = ? AND user_id = ?",
        (keyword, user_id),
    )
    return row[0]["ts"] if row and row[0]["ts"] else None


# ==================== 利润追踪 CRUD ====================

async def add_deal(user_id: str, item_title: str, sell_price: float,
                   cost_price: float = 0, shipping_cost: float = 0,
                   platform_fee: float = 0, notes: str = "") -> int:
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO deals (user_id, item_title, cost_price, sell_price, shipping_cost, platform_fee, notes) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (user_id, item_title, cost_price, sell_price, shipping_cost, platform_fee, notes),
    )
    await db.commit()
    return cursor.lastrowid


async def get_deals(user_id: str, limit: int = 50) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM deals WHERE user_id = ? ORDER BY deal_date DESC LIMIT ?", (user_id, limit)
    )
    return [dict(r) for r in rows]


async def get_profit_summary(user_id: str) -> dict:
    db = await get_db()
    row = await db.execute_fetchall("""
        SELECT
            COUNT(*) as total_deals,
            COALESCE(SUM(sell_price), 0) as total_revenue,
            COALESCE(SUM(cost_price), 0) as total_cost,
            COALESCE(SUM(shipping_cost), 0) as total_shipping,
            COALESCE(SUM(platform_fee), 0) as total_fee,
            COALESCE(SUM(profit), 0) as total_profit
        FROM deals WHERE user_id = ?
    """, (user_id,))
    d = dict(row[0]) if row else {}
    d["profit_margin"] = round((d.get("total_profit", 0) / d.get("total_revenue", 1)) * 100, 1) if d.get("total_revenue") else 0
    return d


# ==================== 管理员统计 ====================

async def get_platform_stats() -> dict:
    db = await get_db()
    users = await db.execute_fetchall("SELECT COUNT(*) as c FROM users")
    deals = await db.execute_fetchall("SELECT COUNT(*) as c FROM deals")
    keywords = await db.execute_fetchall("SELECT COUNT(*) as c FROM keywords")
    return {
        "total_users": users[0]["c"] if users else 0,
        "total_deals": deals[0]["c"] if deals else 0,
        "total_keywords": keywords[0]["c"] if keywords else 0,
    }


# ==================== 客服消息 CRUD ====================

async def save_cs_message(user_id: str, chat_id: str, sender_name: str,
                          content: str, direction: str, msg_time: int) -> int:
    """保存客服消息，返回行 ID"""
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO cs_messages (user_id, chat_id, sender_name, content, direction, msg_time) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, chat_id, sender_name, content, direction, msg_time),
    )
    await db.commit()
    return cursor.lastrowid


async def get_cs_messages(user_id: str, limit: int = 100, chat_id: str = "") -> list[dict]:
    """获取最近客服消息，可按 chat_id 过滤"""
    db = await get_db()
    if chat_id:
        rows = await db.execute_fetchall(
            "SELECT * FROM cs_messages WHERE user_id = ? AND chat_id = ? "
            "ORDER BY msg_time DESC LIMIT ?",
            (user_id, chat_id, limit),
        )
    else:
        rows = await db.execute_fetchall(
            "SELECT * FROM cs_messages WHERE user_id = ? "
            "ORDER BY msg_time DESC LIMIT ?",
            (user_id, limit),
        )
    return [dict(r) for r in rows]


async def clear_cs_messages(user_id: str):
    """清除所有客服消息"""
    db = await get_db()
    await db.execute("DELETE FROM cs_messages WHERE user_id = ?", (user_id,))
    await db.commit()


# ==================== 订单/订阅 CRUD ====================

async def create_order(order_id: str, user_id: str, plan: str,
                       amount: float, payment_method: str = "mock") -> bool:
    """创建订单"""
    db = await get_db()
    await db.execute(
        "INSERT INTO orders (id, user_id, plan, amount, payment_method) VALUES (?, ?, ?, ?, ?)",
        (order_id, user_id, plan, amount, payment_method),
    )
    await db.commit()
    return True


async def mark_order_paid(order_id: str) -> dict | None:
    """标记订单已支付"""
    db = await get_db()
    await db.execute(
        "UPDATE orders SET status = 'paid', paid_at = CURRENT_TIMESTAMP WHERE id = ? AND status = 'pending'",
        (order_id,),
    )
    await db.commit()
    rows = await db.execute_fetchall("SELECT * FROM orders WHERE id = ?", (order_id,))
    return dict(rows[0]) if rows else None


async def get_order(order_id: str) -> dict | None:
    db = await get_db()
    rows = await db.execute_fetchall("SELECT * FROM orders WHERE id = ?", (order_id,))
    return dict(rows[0]) if rows else None


async def get_user_orders(user_id: str, limit: int = 20) -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    )
    return [dict(r) for r in rows]


async def activate_subscription(user_id: str, plan: str, days: int) -> bool:
    """激活订阅：升级用户 tier + 设置到期时间"""
    from datetime import datetime, timedelta
    db = await get_db()

    # 获取当前 tier 信息
    rows = await db.execute_fetchall(
        "SELECT tier, tier_expires_at FROM users WHERE id = ?", (user_id,)
    )
    if not rows:
        return False

    current_tier = rows[0]["tier"]
    current_expires = rows[0]["tier_expires_at"]

    # 如果当前已是 Pro 且未过期，延长到期时间
    now = datetime.utcnow()
    if current_tier == "pro" and current_expires:
        try:
            exp = datetime.fromisoformat(str(current_expires))
            if exp > now:
                start = exp
            else:
                start = now
        except Exception:
            start = now
    else:
        start = now

    new_expires = start + timedelta(days=days)
    await db.execute(
        "UPDATE users SET tier = 'pro', tier_expires_at = ? WHERE id = ?",
        (new_expires.isoformat(), user_id),
    )
    await db.commit()
    return True


async def get_payment_stats() -> dict:
    """管理员：收入统计"""
    db = await get_db()
    rows = await db.execute_fetchall("""
        SELECT
            COUNT(*) as total_orders,
            COALESCE(SUM(CASE WHEN status = 'paid' THEN amount ELSE 0 END), 0) as total_revenue,
            COALESCE(SUM(CASE WHEN status = 'paid' AND plan = 'pro_monthly' THEN 1 ELSE 0 END), 0) as monthly_subs,
            COALESCE(SUM(CASE WHEN status = 'paid' AND plan = 'pro_yearly' THEN 1 ELSE 0 END), 0) as yearly_subs
        FROM orders
    """)
    d = dict(rows[0]) if rows else {}
    pro_users = await db.execute_fetchall(
        "SELECT COUNT(*) as c FROM users WHERE tier = 'pro'"
    )
    d["active_pro_users"] = pro_users[0]["c"] if pro_users else 0
    return d


# ── 价格历史 ──

async def record_price_history(user_id: str, item_id: str, price: float) -> int:
    """记录商品价格变化。返回插入行 ID。"""
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO price_history (user_id, item_id, price) VALUES (?, ?, ?)",
        (user_id, item_id, price),
    )
    await db.commit()
    return cursor.lastrowid


async def get_price_history(item_id: str, user_id: str, limit: int = 100) -> list[dict]:
    """获取商品价格历史"""
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT price, recorded_at FROM price_history "
        "WHERE item_id = ? AND user_id = ? "
        "ORDER BY recorded_at DESC LIMIT ?",
        (item_id, user_id, limit),
    )
    return [dict(r) for r in rows]


async def cleanup_price_history(user_id: str, max_per_item: int = 30):
    """每个 item 只保留最近 N 条记录"""
    db = await get_db()
    await db.execute("""
        DELETE FROM price_history WHERE rowid IN (
            SELECT rowid FROM (
                SELECT rowid,
                       ROW_NUMBER() OVER (PARTITION BY item_id ORDER BY recorded_at DESC) AS rn
                FROM price_history
                WHERE user_id = ?
            ) WHERE rn > ?
        )
    """, (user_id, max_per_item))
    await db.commit()


# ── 邮件配置 ──

async def save_email_config(user_id: str, config: dict) -> bool:
    db = await get_db()
    await db.execute("""
        INSERT INTO email_configs (user_id, smtp_host, smtp_port, sender_email, sender_password,
                                   use_tls, use_ssl, notify_new_items, notify_price_drops, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id) DO UPDATE SET
            smtp_host=excluded.smtp_host, smtp_port=excluded.smtp_port,
            sender_email=excluded.sender_email, sender_password=excluded.sender_password,
            use_tls=excluded.use_tls, use_ssl=excluded.use_ssl,
            notify_new_items=excluded.notify_new_items,
            notify_price_drops=excluded.notify_price_drops,
            updated_at=CURRENT_TIMESTAMP
    """, (
        user_id, config["smtp_host"], config["smtp_port"],
        config["sender_email"], config["sender_password"],
        int(config.get("use_tls", True)), int(config.get("use_ssl", False)),
        int(config.get("notify_new_items", True)),
        int(config.get("notify_price_drops", True)),
    ))
    await db.commit()
    return True


async def get_email_config(user_id: str) -> dict | None:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT * FROM email_configs WHERE user_id = ?", (user_id,),
    )
    if not rows:
        return None
    r = dict(rows[0])
    r["use_tls"] = bool(r["use_tls"])
    r["use_ssl"] = bool(r["use_ssl"])
    r["notify_new_items"] = bool(r["notify_new_items"])
    r["notify_price_drops"] = bool(r["notify_price_drops"])
    return r


async def get_all_email_configs() -> list[dict]:
    db = await get_db()
    rows = await db.execute_fetchall(
        "SELECT user_id, smtp_host, smtp_port, sender_email, sender_password, "
        "use_tls, use_ssl, notify_new_items, notify_price_drops "
        "FROM email_configs WHERE sender_email != '' AND sender_password != ''"
    )
    return [dict(r) for r in rows]
