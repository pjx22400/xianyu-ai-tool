"""闲鱼 AI 助手 — FastAPI 主入口 v0.3

功能：
  - 商品监控（关键词搜索 + 降价检测 + 飞书通知）
  - 智能客服（WebSocket 实时消息 + AI 自动回复 + 订单检测）
  - 多账号管理（JSON 配置，独立 cookies）
  - 自动擦亮（定时刷新商品保持曝光）
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from src.config import config
from src.database import init_db, add_keyword, get_keywords, delete_keyword, toggle_keyword, get_items, close_db
from src.database import add_deal, get_deals, get_profit_summary
from src.models import KeywordCreate, MonitorKeyword, DealCreate
from src.monitor import Monitor
from src.xianyu_ws import XianyuWebSocket
from src.reply_agent import ReplyAgent
from src.accounts import account_manager, Account
from src.auto_refresh import AutoRefresher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("main")

# 文件日志（按 10MB 轮转，保留 5 个备份）
_log_dir = config.BASE_DIR / "logs"
_log_dir.mkdir(exist_ok=True)
_file_handler = RotatingFileHandler(
    _log_dir / "xianyu.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
logging.getLogger().addHandler(_file_handler)
logging.getLogger("uvicorn.access").addHandler(_file_handler)

# 全局服务
monitor: Monitor | None = None
ws_client: XianyuWebSocket | None = None
reply_agent: ReplyAgent | None = None
auto_refresher: AutoRefresher | None = None
cs_running = False
refresh_running = False


def _has_cookies() -> bool:
    return bool(account_manager.default_cookies or (
        config.XIANYU_COOKIES and config.XIANYU_COOKIES != "your_cookies_here"
    ))


@asynccontextmanager
async def lifespan(app: FastAPI):
    global monitor, reply_agent
    config.ensure_dirs()
    await init_db()
    logger.info(f"数据库初始化完成: {config.DATA_DIR}/xianyu.db")

    # 初始化 AI 回复引擎
    reply_agent = ReplyAgent(
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_BASE_URL,
        model=config.DEEPSEEK_MODEL,
    )

    # 启动商品监控 + 客服
    if _has_cookies():
        monitor = Monitor()
        monitor.start()
        logger.info("商品监控已启动")

        # 启动自动擦亮（默认每 6 小时）
        global auto_refresher, refresh_running
        auto_refresher = AutoRefresher(interval_minutes=360)
        auto_refresher.start()
        refresh_running = True
        logger.info("自动擦亮已启动，间隔 360 分钟")

        # 客服 WebSocket（后台尝试启动，失败不阻塞服务）
        asyncio.create_task(_try_start_cs())
    else:
        logger.warning("未配置账号，监控、擦亮和客服未启动")

    yield

    if monitor:
        monitor.stop()
        await monitor.close()
    if auto_refresher:
        auto_refresher.stop()
    await _stop_cs()
    if reply_agent:
        await reply_agent.close()
    await close_db()
    logger.info("服务已停止")


app = FastAPI(title="闲鱼 AI 智能助手", version="0.3.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ==================== 通用 ====================

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "monitor_running": monitor is not None and monitor._running,
        "cs_running": cs_running,
        "refresh_running": refresh_running,
    }


# ==================== 关键词管理 ====================

@app.get("/api/keywords")
async def list_keywords():
    keywords = await get_keywords(enabled_only=False)
    return [kw.model_dump() for kw in keywords]


@app.post("/api/keywords")
async def create_keyword(body: KeywordCreate):
    await add_keyword(MonitorKeyword(**body.model_dump()))
    return {"ok": True}


@app.delete("/api/keywords/{keyword}")
async def remove_keyword(keyword: str):
    await delete_keyword(keyword)
    return {"ok": True}


@app.put("/api/keywords/{keyword}/toggle")
async def toggle_keyword_endpoint(keyword: str, enabled: bool = True):
    await toggle_keyword(keyword, enabled)
    return {"ok": True}


# ==================== 商品查询 ====================

@app.get("/api/items")
async def list_items(keyword: str = "", limit: int = 50):
    if not keyword:
        return []
    raw = await get_items(keyword, limit=limit)
    return [it.model_dump() for it in raw]


# ==================== 手动扫描 ====================

@app.post("/api/scan")
async def trigger_scan(keyword: str = ""):
    if monitor is None:
        raise HTTPException(400, "监控未启动，请先配置账号")
    if keyword:
        return await monitor.scan_keyword(keyword)
    return {"results": await monitor.scan_all()}


# ==================== 状态 ====================

@app.get("/api/status")
async def get_status():
    keywords = await get_keywords(enabled_only=True)
    kw_list = []
    for kw in keywords:
        items = await get_items(kw.keyword, limit=1)
        kw_list.append({
            "keyword": kw.keyword,
            "enabled": kw.enabled,
            "item_count": len(items),
            "last_scan": items[0].last_seen.isoformat() if items and items[0].last_seen else None,
        })
    return {
        "monitor_running": monitor is not None and monitor._running,
        "cs_running": cs_running,
        "refresh_running": refresh_running,
        "interval_s": config.MONITOR_INTERVAL,
        "keywords": kw_list,
    }


# ==================== 智能客服 ====================

cs_messages: list[dict] = []


async def _on_buyer_message(info: dict):
    """处理买家消息回调"""
    cs_messages.append({
        "chat_id": info["chat_id"],
        "sender_name": info["sender_name"],
        "content": info["content"],
        "time": info["create_time"],
        "direction": "in",
    })

    # AI 生成回复
    item_desc = f"商品ID: {info.get('item_id', '未知')}"
    reply = await reply_agent.generate_reply(
        user_msg=info["content"],
        item_desc=item_desc,
        chat_id=info["chat_id"],
        sender_id=info["sender_id"],
    )

    # 发送回复
    await ws_client.send_reply(info["chat_id"], info["sender_id"], reply)

    cs_messages.append({
        "chat_id": info["chat_id"],
        "sender_name": "AI 助手",
        "content": reply,
        "time": int(asyncio.get_event_loop().time() * 1000),
        "direction": "out",
    })

    # 保留最近 200 条
    while len(cs_messages) > 200:
        cs_messages.pop(0)

    logger.info(f"💬 回复 [{info['chat_id']}]: {reply[:50]}")


async def _on_order_event(order_info: dict):
    """处理订单状态变更"""
    status = order_info.get("status", "")
    order_id = order_info.get("order_id", "")
    item_title = order_info.get("item_title", "")
    buyer = order_info.get("buyer_name", "")

    msg = f"📦 订单更新: {status} — {item_title} (订单号: {order_id})"
    logger.info(msg)

    cs_messages.append({
        "chat_id": order_id,
        "sender_name": "系统",
        "content": msg,
        "time": order_info.get("create_time", int(asyncio.get_event_loop().time() * 1000)),
        "direction": "system",
        "order_status": status,
        "order_id": order_id,
        "item_title": item_title,
        "buyer": buyer,
    })

    # 检测到「等待卖家发货」— 自动提醒
    if "WAIT_SELLER_SEND_GOODS" in str(status) or "等待卖家发货" in str(status):
        reminder = (
            f"✅ 买家 {buyer} 已付款！\n"
            f"商品: {item_title}\n订单号: {order_id}\n"
            f"请尽快发货～"
        )
        cs_messages.append({
            "chat_id": order_id,
            "sender_name": "系统",
            "content": reminder,
            "time": int(asyncio.get_event_loop().time() * 1000),
            "direction": "system",
            "auto_action": "发货提醒",
        })

    while len(cs_messages) > 200:
        cs_messages.pop(0)


async def _try_start_cs():
    """后台尝试启动客服，失败不阻塞服务"""
    try:
        await _start_cs()
    except Exception as e:
        logger.warning(f"客服启动失败（可稍后手动启动）: {e}")


async def _start_cs():
    global ws_client, cs_running
    if cs_running:
        return
    if not _has_cookies():
        raise HTTPException(400, "请先配置账号")

    cookies = account_manager.default_cookies or config.XIANYU_COOKIES
    ws_client = XianyuWebSocket(cookies)
    ws_client.on_message(_on_buyer_message)
    ws_client.on_order(_on_order_event)
    try:
        await ws_client.start()
        cs_running = True
        logger.info("智能客服已启动（含订单检测）")
    except Exception as e:
        logger.error(f"客服启动失败: {e}")
        raise HTTPException(500, f"客服启动失败: {e}")


async def _stop_cs():
    global ws_client, cs_running
    if ws_client:
        await ws_client.stop()
        ws_client = None
    cs_running = False


@app.post("/api/cs/start")
async def start_cs():
    if cs_running:
        return {"ok": True, "message": "已在运行"}
    await _start_cs()
    return {"ok": True}


@app.post("/api/cs/stop")
async def stop_cs():
    await _stop_cs()
    return {"ok": True}


@app.get("/api/cs/messages")
async def get_cs_messages(limit: int = 50):
    return cs_messages[-limit:]


@app.get("/api/cs/status")
async def cs_status():
    return {
        "running": cs_running,
        "message_count": len(cs_messages),
        "my_id": ws_client.my_id if ws_client else "",
    }


# ==================== 多账号管理 ====================

@app.get("/api/accounts")
async def list_accounts():
    return [a.model_dump() for a in account_manager.list()]


@app.post("/api/login/callback")
async def login_callback(body: dict):
    """从浏览器控制台回传 Cookie（自动新增或更新）"""
    acc_id = body.get("id", "")
    name = body.get("name", "")
    cookies = body.get("cookies", "")
    if not acc_id or not cookies:
        raise HTTPException(400, "缺少 id 或 cookies")

    existing = account_manager.get(acc_id)
    if existing:
        account_manager.update(acc_id, cookies=cookies, name=name or existing.name)
        logger.info(f"更新账号 Cookie: {acc_id}")
        return {"ok": True, "id": acc_id, "action": "updated"}
    else:
        account = Account(id=acc_id, name=name or acc_id, cookies=cookies, enabled=True, is_default=len(account_manager.list()) == 0)
        account_manager.add(account)
        logger.info(f"新增账号: {acc_id}")
        return {"ok": True, "id": acc_id, "action": "created"}


@app.post("/api/accounts")
async def add_account(body: Account):
    """添加账号（如果已存在则更新 Cookie）"""
    existing = account_manager.get(body.id)
    if existing:
        account_manager.update(body.id, cookies=body.cookies, name=body.name or existing.name)
        return {"ok": True, "id": body.id, "action": "updated"}
    if account_manager.add(body):
        return {"ok": True, "id": body.id, "action": "created"}
    raise HTTPException(400, f"添加账号失败")


@app.put("/api/accounts/{account_id}")
async def update_account(account_id: str, body: dict):
    if account_manager.update(account_id, **body):
        return {"ok": True}
    raise HTTPException(404, "账号不存在")


@app.delete("/api/accounts/{account_id}")
async def remove_account(account_id: str):
    if account_manager.remove(account_id):
        return {"ok": True}
    raise HTTPException(404, "账号不存在")


@app.post("/api/accounts/{account_id}/set-default")
async def set_default_account(account_id: str):
    if account_manager.set_default(account_id):
        return {"ok": True}
    raise HTTPException(404, "账号不存在")


# ==================== 自动擦亮 ====================

@app.get("/api/refresh/status")
async def refresh_status():
    return {
        "running": refresh_running,
        "interval_minutes": auto_refresher.interval // 60 if auto_refresher else 360,
    }


@app.post("/api/refresh/now")
async def trigger_refresh():
    if auto_refresher is None:
        raise HTTPException(400, "自动擦亮未启动，请先配置账号")
    result = await auto_refresher.refresh_all([])
    return result


# ==================== 静态文件 ====================


# ==================== 利润追踪 ====================

@app.get("/api/deals/summary")
async def deals_summary():
    return await get_profit_summary()


@app.get("/api/deals")
async def list_deals(limit: int = 50):
    return await get_deals(limit)


@app.post("/api/deals")
async def create_deal(deal: DealCreate):
    id_ = await add_deal(
        item_title=deal.item_title,
        sell_price=deal.sell_price,
        cost_price=deal.cost_price,
        shipping_cost=deal.shipping_cost,
        platform_fee=deal.platform_fee,
        notes=deal.notes,
    )
    return {"ok": True, "id": id_}


# ==================== 客服统计 ====================

@app.get("/api/cs/stats")
async def cs_stats():
    if reply_agent is None:
        return {"error": "客服未启动"}
    s = reply_agent.stats
    return {
        "total_replies": s.total,
        "price_negotiation": s.price,
        "deal_intent": s.deal,
        "greeting": s.greeting,
        "tech_questions": s.tech,
        "shipping": s.shipping,
        "other": s.other,
        "active_conversations": len(reply_agent._conversations),
    }


# ==================== 静态文件 ====================

@app.get("/")
async def index():
    return FileResponse(str(config.BASE_DIR / "frontend" / "dashboard.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host=config.HOST, port=config.PORT, reload=True)
