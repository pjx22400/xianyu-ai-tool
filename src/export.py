"""数据导出模块 — CSV 导出 v0.6

支持导出：关键词、商品、利润交易、订单记录
"""

import csv
import io
from datetime import datetime
from typing import Optional

from src.database import (
    get_keywords, get_items, get_deals, get_user_orders,
    get_cs_messages, DEFAULT_USER_ID,
)


async def export_keywords_csv(user_id: str) -> str:
    """导出关键词到 CSV 字符串"""
    keywords = await get_keywords(user_id, enabled_only=False)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["关键词", "最低价", "最高价", "启用", "创建时间"])
    for kw in keywords:
        writer.writerow([
            kw.keyword,
            kw.min_price or "",
            kw.max_price or "",
            "是" if kw.enabled else "否",
            kw.created_at.isoformat() if kw.created_at else "",
        ])
    return output.getvalue()


async def export_items_csv(user_id: str, keyword: str = "") -> str:
    """导出商品到 CSV 字符串"""
    items = await get_items(keyword or "%", user_id, limit=5000) if not keyword else \
            await get_items(keyword, user_id, limit=5000)
    if not keyword:
        # 获取所有关键词的商品
        from src.database import get_db
        db = await get_db()
        rows = await db.execute_fetchall(
            "SELECT * FROM items WHERE user_id = ? ORDER BY last_seen DESC LIMIT 5000",
            (user_id,),
        )
        from src.models import XianyuItem
        items = [XianyuItem(**dict(r)) for r in rows]

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "商品ID", "标题", "当前价格", "原始价格", "降价金额",
        "卖家", "所在地", "关键词", "首次发现", "最后发现", "是否新品", "是否降价",
    ])
    for it in items:
        writer.writerow([
            it.item_id, it.title, it.price, it.old_price or "",
            it.price_drop_amount, it.seller, it.location, it.keyword,
            it.first_seen.isoformat() if it.first_seen else "",
            it.last_seen.isoformat() if it.last_seen else "",
            "是" if it.is_new else "否",
            "是" if it.price_dropped else "否",
        ])
    return output.getvalue()


async def export_deals_csv(user_id: str) -> str:
    """导出利润交易到 CSV 字符串"""
    deals = await get_deals(user_id, limit=5000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "商品名称", "进货价", "卖出价", "运费", "平台费",
        "利润", "利润率", "成交时间", "备注",
    ])
    for d in deals:
        profit = d.get("profit", 0) or 0
        revenue = d.get("sell_price", 0) or 0
        margin = f"{(profit / revenue * 100):.1f}%" if revenue > 0 else "0%"
        writer.writerow([
            d.get("item_title", ""), d.get("cost_price", 0),
            d.get("sell_price", 0), d.get("shipping_cost", 0),
            d.get("platform_fee", 0), profit, margin,
            d.get("deal_date", ""), d.get("notes", ""),
        ])
    return output.getvalue()


async def export_orders_csv(user_id: str) -> str:
    """导出支付订单到 CSV 字符串"""
    orders = await get_user_orders(user_id, limit=5000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["订单ID", "方案", "金额", "状态", "支付方式", "创建时间", "支付时间"])
    for o in orders:
        writer.writerow([
            o.get("id", ""), o.get("plan", ""), o.get("amount", 0),
            o.get("status", ""), o.get("payment_method", ""),
            o.get("created_at", ""), o.get("paid_at", ""),
        ])
    return output.getvalue()


async def export_full_csv(user_id: str) -> str:
    """完整数据包导出（多个表格）"""
    parts = []
    parts.append("=== 关键词 ===\n" + await export_keywords_csv(user_id) + "\n")
    parts.append("=== 商品 ===\n" + await export_items_csv(user_id) + "\n")
    parts.append("=== 利润交易 ===\n" + await export_deals_csv(user_id) + "\n")
    parts.append("=== 支付订单 ===\n" + await export_orders_csv(user_id) + "\n")
    return "\n".join(parts)
