"""飞书通知模块 — 走 Bot API 直接推送给用户"""
import logging
import httpx
from src.config import config

logger = logging.getLogger("notifier")

_token_cache: dict = {"token": "", "expires": 0}


async def _get_access_token() -> str:
    """获取 tenant_access_token（缓存）"""
    import time
    now = time.time()
    if _token_cache["token"] and _token_cache["expires"] > now + 60:
        return _token_cache["token"]

    resp = httpx.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": config.FEISHU_APP_ID, "app_secret": config.FEISHU_APP_SECRET},
        timeout=10,
    )
    data = resp.json()
    _token_cache["token"] = data["tenant_access_token"]
    _token_cache["expires"] = now + data.get("expire", 7200)
    return _token_cache["token"]


async def send_feishu(content: str) -> bool:
    """发送飞书消息给用户"""
    user_id = config.FEISHU_USER_OPEN_ID
    if not user_id:
        logger.info(f"📢 [通知日志] {content[:200]}")
        return False

    try:
        token = await _get_access_token()
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=open_id",
                headers={"Authorization": f"Bearer {token}"},
                json={
                    "receive_id": user_id,
                    "msg_type": "text",
                    "content": json.dumps({"text": content}),
                },
            )
            ok = resp.status_code == 200
            if not ok:
                logger.error(f"飞书推送失败 [{resp.status_code}]: {resp.text[:200]}")
            return ok
    except Exception as e:
        logger.error(f"飞书推送异常: {e}")
        return False


import json


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
