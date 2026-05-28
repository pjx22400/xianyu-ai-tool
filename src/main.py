"""闲鱼 AI 助手 — FastAPI 主入口 v0.5 SaaS

多租户架构：
  - JWT 认证（注册/登录/刷新）
  - user_id 数据隔离
  - 免费版/Pro 版功能分层
  - 管理员面板
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from typing import Optional

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from src.config import config
from src.database import (
    init_db, close_db,
    add_keyword, get_keywords, count_keywords, delete_keyword, toggle_keyword,
    get_items, add_deal, get_deals, get_profit_summary,
    create_user, get_user_by_email, get_user_by_id, get_all_users, get_platform_stats,
    save_refresh_token, verify_refresh_token, revoke_refresh_token, DEFAULT_USER_ID,
    save_cs_message, get_cs_messages, clear_cs_messages,
)
from src.models import KeywordCreate, MonitorKeyword, DealCreate, RegisterRequest, LoginRequest
from src.auth import (
    hash_password, verify_password, create_access_token, create_refresh_token,
    verify_access_token, get_tier_config, check_feature, REFRESH_TOKEN_TTL,
)
from src.monitor import Monitor
from src.xianyu_ws import XianyuWebSocket
from src.reply_agent import ReplyAgent
from src.accounts import account_manager, Account
from src.auto_refresh import AutoRefresher

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("main")

_log_dir = config.BASE_DIR / "logs"
_log_dir.mkdir(exist_ok=True)
_file_handler = RotatingFileHandler(
    _log_dir / "xianyu.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
_file_handler.setFormatter(logging.Formatter("%(asctime)s [%(name)s] %(levelname)s: %(message)s"))
logging.getLogger().addHandler(_file_handler)
logging.getLogger("uvicorn.access").addHandler(_file_handler)

monitor: Monitor | None = None
ws_client: XianyuWebSocket | None = None
reply_agent: ReplyAgent | None = None
auto_refresher: AutoRefresher | None = None
cs_running = False
refresh_running = False

security = HTTPBearer(auto_error=False)


def _has_cookies() -> bool:
    return bool(account_manager.default_cookies or (
        config.XIANYU_COOKIES and config.XIANYU_COOKIES != "your_cookies_here"
    ))


async def _get_user_id(request: Request) -> str:
    """从 JWT 提取 user_id，无 token 时回退到默认用户（向后兼容）"""
    credentials: Optional[HTTPAuthorizationCredentials] = await security(request)
    if credentials:
        payload = verify_access_token(credentials.credentials)
        if payload:
            return payload["sub"]
    return DEFAULT_USER_ID


async def _require_auth(request: Request) -> str:
    """强制认证，无有效 token 返回 401"""
    credentials: Optional[HTTPAuthorizationCredentials] = await security(request)
    if not credentials:
        raise HTTPException(401, "请先登录")
    payload = verify_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(401, "登录已过期，请重新登录")
    return payload["sub"]


# ==================== App ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    global monitor, reply_agent
    config.ensure_dirs()
    await init_db()
    logger.info(f"数据库初始化完成: {config.DATA_DIR}/xianyu.db")

    reply_agent = ReplyAgent(
        api_key=config.DEEPSEEK_API_KEY,
        base_url=config.DEEPSEEK_BASE_URL,
        model=config.DEEPSEEK_MODEL,
    )

    if _has_cookies():
        monitor = Monitor()
        monitor.start()
        logger.info("商品监控已启动")

        global auto_refresher, refresh_running
        auto_refresher = AutoRefresher(interval_minutes=360)
        auto_refresher.start()
        refresh_running = True
        logger.info("自动擦亮已启动")

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


app = FastAPI(title="闲鱼 AI 智能助手", version="0.5.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ==================== 认证 ====================

@app.post("/api/auth/register")
async def register(body: RegisterRequest):
    """用户注册"""
    existing = await get_user_by_email(body.email)
    if existing:
        raise HTTPException(400, "该邮箱已注册")
    if len(body.password) < 6:
        raise HTTPException(400, "密码至少 6 位")

    pw_hash = hash_password(body.password)
    user_id = await create_user(body.email, pw_hash)
    logger.info(f"新用户注册: {body.email}")

    access_token = create_access_token(user_id, body.email, "free")
    refresh_token = create_refresh_token(user_id)
    expires = (datetime.utcnow() + timedelta(seconds=REFRESH_TOKEN_TTL)).isoformat()
    await save_refresh_token(user_id, refresh_token, expires)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {"id": user_id, "email": body.email, "tier": "free"},
    }


@app.post("/api/auth/login")
async def login(body: LoginRequest):
    """用户登录"""
    user = await get_user_by_email(body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "邮箱或密码错误")

    access_token = create_access_token(user["id"], user["email"], user["tier"])
    refresh_token = create_refresh_token(user["id"])
    expires = (datetime.utcnow() + timedelta(seconds=REFRESH_TOKEN_TTL)).isoformat()
    await save_refresh_token(user["id"], refresh_token, expires)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {"id": user["id"], "email": user["email"], "tier": user["tier"]},
    }


@app.post("/api/auth/refresh")
async def refresh_token(body: dict):
    """刷新 access token"""
    token = body.get("refresh_token", "")
    if not token:
        raise HTTPException(400, "缺少 refresh_token")

    user_id = await verify_refresh_token(token)
    if not user_id:
        raise HTTPException(401, "refresh_token 无效或已过期")

    await revoke_refresh_token(token)

    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(401, "用户不存在")

    access_token = create_access_token(user_id, user["email"], user["tier"])
    new_refresh = create_refresh_token(user_id)
    expires = (datetime.utcnow() + timedelta(seconds=REFRESH_TOKEN_TTL)).isoformat()
    await save_refresh_token(user_id, new_refresh, expires)

    return {"access_token": access_token, "refresh_token": new_refresh}


@app.get("/api/auth/me")
async def me(request: Request):
    """获取当前用户信息"""
    user_id = await _require_auth(request)
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(401, "用户不存在")
    config = get_tier_config(user["tier"])
    return {
        "id": user["id"],
        "email": user["email"],
        "tier": user["tier"],
        "tier_name": config["name"],
        "tier_expires_at": user.get("tier_expires_at"),
        "features": {k: v for k, v in config.items() if isinstance(v, bool)},
    }


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
async def list_keywords(request: Request):
    user_id = await _get_user_id(request)
    keywords = await get_keywords(user_id, enabled_only=False)
    return [kw.model_dump() for kw in keywords]


@app.post("/api/keywords")
async def create_keyword(body: KeywordCreate, request: Request):
    user_id = await _require_auth(request)
    tier = get_tier_config((await get_user_by_id(user_id))["tier"])
    current_count = await count_keywords(user_id)
    if current_count >= tier["max_keywords"]:
        raise HTTPException(403, f"免费版最多 {tier['max_keywords']} 个关键词，升级 Pro 解锁更多")
    await add_keyword(MonitorKeyword(**body.model_dump()), user_id)
    return {"ok": True}


@app.delete("/api/keywords/{keyword}")
async def remove_keyword(keyword: str, request: Request):
    user_id = await _get_user_id(request)
    await delete_keyword(keyword, user_id)
    return {"ok": True}


@app.put("/api/keywords/{keyword}/toggle")
async def toggle_keyword_endpoint(keyword: str, request: Request, enabled: bool = True):
    user_id = await _get_user_id(request)
    await toggle_keyword(keyword, enabled, user_id)
    return {"ok": True}


# ==================== 商品查询 ====================

@app.get("/api/items")
async def list_items(request: Request, keyword: str = "", limit: int = 50):
    if not keyword:
        return []
    user_id = await _get_user_id(request)
    raw = await get_items(keyword, user_id, limit=limit)
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
async def get_status(request: Request):
    user_id = await _get_user_id(request)
    keywords = await get_keywords(user_id, enabled_only=True)
    kw_list = []
    for kw in keywords:
        items = await get_items(kw.keyword, user_id, limit=1)
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

# 速率限制：每个 chat_id 最后回复时间
_last_reply_time: dict[str, float] = {}
_REPLY_COOLDOWN = 5  # 同一会话至少间隔 5 秒


async def _on_buyer_message(info: dict):
    chat_id = info["chat_id"]
    msg_time = info["create_time"]

    # 持久化到 DB
    await save_cs_message(
        user_id=DEFAULT_USER_ID,
        chat_id=chat_id,
        sender_name=info["sender_name"],
        content=info["content"],
        direction="in",
        msg_time=msg_time,
    )

    # 速率限制
    now = asyncio.get_event_loop().time()
    if chat_id in _last_reply_time and (now - _last_reply_time[chat_id]) < _REPLY_COOLDOWN:
        logger.debug(f"⏳ [{chat_id}] 冷却中，跳过自动回复")
        return

    _last_reply_time[chat_id] = now

    item_desc = f"商品ID: {info.get('item_id', '未知')}"
    reply = await reply_agent.generate_reply(
        user_msg=info["content"],
        item_desc=item_desc,
        chat_id=chat_id,
        sender_id=info["sender_id"],
    )

    await ws_client.send_reply(chat_id, info["sender_id"], reply)

    # 持久化回复到 DB
    await save_cs_message(
        user_id=DEFAULT_USER_ID,
        chat_id=chat_id,
        sender_name="AI 助手",
        content=reply,
        direction="out",
        msg_time=int(now * 1000),
    )

    logger.info(f"💬 回复 [{chat_id}]: {reply[:50]}")


async def _on_order_event(order_info: dict):
    status = order_info.get("status", "")
    order_id = order_info.get("order_id", "")
    item_title = order_info.get("item_title", "")
    buyer = order_info.get("buyer_name", "")

    msg = f"📦 订单更新: {status} — {item_title} (订单号: {order_id})"
    logger.info(msg)

    await save_cs_message(
        user_id=DEFAULT_USER_ID,
        chat_id=order_id,
        sender_name="系统",
        content=msg,
        direction="system",
        msg_time=order_info.get("create_time", int(asyncio.get_event_loop().time() * 1000)),
    )

    if "WAIT_SELLER_SEND_GOODS" in str(status) or "等待卖家发货" in str(status):
        reminder = (
            f"✅ 买家 {buyer} 已付款！\n"
            f"商品: {item_title}\n订单号: {order_id}\n"
            f"请尽快发货～"
        )
        await save_cs_message(
            user_id=DEFAULT_USER_ID,
            chat_id=order_id,
            sender_name="系统",
            content=reminder,
            direction="system",
            msg_time=int(asyncio.get_event_loop().time() * 1000),
        )


async def _try_start_cs():
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
async def get_cs_messages_endpoint(request: Request, limit: int = 100):
    user_id = await _get_user_id(request)
    msgs = await get_cs_messages(user_id, limit=limit)
    return msgs


@app.get("/api/cs/status")
async def cs_status():
    return {
        "running": cs_running,
        "my_id": ws_client.my_id if ws_client else "",
    }


@app.post("/api/cs/reply")
async def manual_reply(body: dict, request: Request):
    """手动发送回复（覆盖 AI 自动回复）"""
    if not ws_client or not cs_running:
        raise HTTPException(400, "客服未启动")
    chat_id = body.get("chat_id", "")
    text = body.get("text", "")
    if not chat_id or not text:
        raise HTTPException(400, "缺少 chat_id 或 text")

    # 拼发送方 ID（从 chat_id 提取）
    to_id = chat_id  # 闲鱼 chat_id 即对方 ID

    try:
        await ws_client.send_reply(chat_id, to_id, text)
    except Exception as e:
        logger.error(f"手动回复失败: {e}")
        raise HTTPException(500, f"发送失败: {str(e)[:80]}")

    user_id = await _get_user_id(request)
    await save_cs_message(
        user_id=user_id,
        chat_id=chat_id,
        sender_name="手动回复",
        content=text,
        direction="out",
        msg_time=int(asyncio.get_event_loop().time() * 1000),
    )

    logger.info(f"✋ 手动回复 [{chat_id}]: {text[:50]}")
    return {"ok": True}


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


# ==================== 多账号管理 ====================

@app.get("/api/accounts")
async def list_accounts():
    return [a.model_dump() for a in account_manager.list()]


@app.post("/api/login/callback")
async def login_callback(body: dict):
    acc_id = body.get("id", "")
    name = body.get("name", "")
    cookies = body.get("cookies", "")
    if not acc_id or not cookies:
        raise HTTPException(400, "缺少 id 或 cookies")

    existing = account_manager.get(acc_id)
    if existing:
        account_manager.update(acc_id, cookies=cookies, name=name or existing.name)
        return {"ok": True, "id": acc_id, "action": "updated"}
    else:
        account = Account(id=acc_id, name=name or acc_id, cookies=cookies, enabled=True,
                         is_default=len(account_manager.list()) == 0)
        account_manager.add(account)
        return {"ok": True, "id": acc_id, "action": "created"}


@app.post("/api/accounts")
async def add_account(body: Account):
    existing = account_manager.get(body.id)
    if existing:
        account_manager.update(body.id, cookies=body.cookies, name=body.name or existing.name)
        return {"ok": True, "id": body.id, "action": "updated"}
    if account_manager.add(body):
        return {"ok": True, "id": body.id, "action": "created"}
    raise HTTPException(400, "添加账号失败")


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
        raise HTTPException(400, "自动擦亮未启动")
    result = await auto_refresher.refresh_all([])
    return result


# ==================== 利润追踪 ====================

@app.get("/api/deals/summary")
async def deals_summary(request: Request):
    user_id = await _get_user_id(request)
    return await get_profit_summary(user_id)


@app.get("/api/deals")
async def list_deals(request: Request, limit: int = 50):
    user_id = await _get_user_id(request)
    return await get_deals(user_id, limit)


@app.post("/api/deals")
async def create_deal(deal: DealCreate, request: Request):
    user_id = await _get_user_id(request)
    id_ = await add_deal(
        user_id=user_id,
        item_title=deal.item_title,
        sell_price=deal.sell_price,
        cost_price=deal.cost_price,
        shipping_cost=deal.shipping_cost,
        platform_fee=deal.platform_fee,
        notes=deal.notes,
    )
    return {"ok": True, "id": id_}


# ==================== 管理员 ====================

@app.get("/api/admin/stats")
async def admin_stats(request: Request):
    user_id = await _require_auth(request)
    user = await get_user_by_id(user_id)
    # 简单管理：默认用户是 admin
    if user_id != DEFAULT_USER_ID:
        raise HTTPException(403, "无权限")
    return await get_platform_stats()


@app.get("/api/admin/users")
async def admin_users(request: Request):
    user_id = await _require_auth(request)
    if user_id != DEFAULT_USER_ID:
        raise HTTPException(403, "无权限")
    users = await get_all_users()
    return users


# ==================== 静态文件 ====================

@app.get("/dashboard")
@app.get("/app")
async def dashboard():
    return FileResponse(str(config.BASE_DIR / "frontend" / "dashboard.html"))


@app.get("/login")
async def login_page():
    return FileResponse(str(config.BASE_DIR / "frontend" / "login.html"))


@app.get("/")
async def index(request: Request):
    """未登录显示 Landing，已登录跳转 Dashboard"""
    user_id = await _get_user_id(request)
    if user_id != DEFAULT_USER_ID:
        return FileResponse(str(config.BASE_DIR / "frontend" / "dashboard.html"))
    return FileResponse(str(config.BASE_DIR / "frontend" / "landing.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host=config.HOST, port=config.PORT, reload=True)
