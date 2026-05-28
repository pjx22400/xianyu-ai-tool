"""飞书通知模块 — 写入通知文件，由 Hermes cron job 轮询推送"""
import json
import logging
from pathlib import Path
from datetime import datetime

logger = logging.getLogger("notifier")

NOTIFY_DIR = Path("/app/notifications")
NOTIFY_DIR.mkdir(parents=True, exist_ok=True)


def _push(notification_type: str, payload: dict):
    """写入通知到 JSON 文件"""
    entry = {
        "type": notification_type,
        "payload": payload,
        "ts": datetime.now().isoformat(),
    }
    # 用时间戳+随机后缀避免文件名冲突
    fname = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{notification_type}.json"
    fpath = NOTIFY_DIR / fname
    with open(fpath, "w") as f:
        json.dump(entry, f, ensure_ascii=False)


async def send_feishu(content: str) -> bool:
    """写入文本通知"""
    try:
        _push("text", {"content": content})
        return True
    except Exception as e:
        logger.error(f"通知写入失败: {e}")
        return False


async def notify_new_items(items: list[dict]):
    if not items:
        return

    lines = [f"🆕 闲鱼监控 — 新商品 ({len(items)} 件)\n"]
    for it in items[:10]:
        price = it.get("price", 0)
        title = it.get("title", "无标题")[:40]
        seller = it.get("seller", "?")
        item_id = it.get("item_id", "")
        lines.append(f"• ¥{price} {title}")
        lines.append(f"  卖家: {seller} | https://www.goofish.com/item?id={item_id}")

    if len(items) > 10:
        lines.append(f"\n... 还有 {len(items) - 10} 件")

    await send_feishu("\n".join(lines))


async def notify_price_drops(items: list[dict]):
    if not items:
        return

    lines = [f"📉 闲鱼监控 — 降价提醒 ({len(items)} 件)\n"]
    for it in items[:10]:
        price = it.get("price", 0)
        old_price = it.get("old_price", 0)
        drop = it.get("price_drop_amount", 0)
        title = it.get("title", "无标题")[:40]
        item_id = it.get("item_id", "")
        lines.append(f"• ¥{old_price} → ¥{price} (降 ¥{drop})")
        lines.append(f"  {title} | https://www.goofish.com/item?id={item_id}")

    if len(items) > 10:
        lines.append(f"\n... 还有 {len(items) - 10} 件")

    await send_feishu("\n".join(lines))
