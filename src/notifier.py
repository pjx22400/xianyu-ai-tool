"""飞书通知模块 — 降价提醒 + 新商品通知"""
import logging
import httpx
from src.config import config

logger = logging.getLogger("notifier")

# 飞书消息卡片模板
CARD_TEMPLATE = """{{"msg_type":"interactive","card":{{"header":{{"title":{{"tag":"plain_text","content":"{title}"}},"template":"red"}},"elements":[{elements}]}}}}"""


async def _send_feishu(content: str) -> bool:
    """通过 webhook 发送飞书消息，无 webhook 则仅日志"""
    webhook = config.FEISHU_WEBHOOK
    if not webhook:
        logger.info(f"📢 [通知日志] {content[:200]}")
        return False

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook, json={"msg_type": "text", "content": {"text": content}})
            return resp.status_code == 200
    except Exception as e:
        logger.error(f"飞书通知发送失败: {e}")
        return False


async def notify_new_items(items: list[dict]):
    """通知新上架商品"""
    if not items:
        return

    lines = [f"🆕 **闲鱼监控 — 新商品 ({len(items)} 件)**\n"]
    for it in items[:10]:  # 最多显示 10 条
        price = it.get("price", 0)
        title = it.get("title", "无标题")[:40]
        seller = it.get("seller", "?")
        item_id = it.get("item_id", "")
        lines.append(f"• **¥{price}** {title}")
        lines.append(f"  卖家: {seller} | [查看](https://www.goofish.com/item?id={item_id})")

    if len(items) > 10:
        lines.append(f"\n... 还有 {len(items) - 10} 件")

    await _send_feishu("\n".join(lines))


async def notify_price_drops(items: list[dict]):
    """通知降价商品"""
    if not items:
        return

    lines = [f"📉 **闲鱼监控 — 降价提醒 ({len(items)} 件)**\n"]
    for it in items[:10]:
        price = it.get("price", 0)
        old_price = it.get("old_price", 0)
        drop = it.get("price_drop_amount", 0)
        title = it.get("title", "无标题")[:40]
        item_id = it.get("item_id", "")
        lines.append(f"• **¥{old_price} → ¥{price}** (降 ¥{drop})")
        lines.append(f"  {title} | [查看](https://www.goofish.com/item?id={item_id})")

    if len(items) > 10:
        lines.append(f"\n... 还有 {len(items) - 10} 件")

    await _send_feishu("\n".join(lines))
