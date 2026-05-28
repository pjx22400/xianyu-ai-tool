"""闲鱼 AI 助手 — FastAPI 主入口 v0.2

功能：
  - 商品监控（关键词搜索 + 降价检测 + 飞书通知）
  - 智能客服（WebSocket 实时消息 + AI 自动回复）
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from src.config import config
from src.database import init_db, add_keyword, get_keywords, delete_keyword, toggle_keyword, get_items
from src.models import KeywordCreate, MonitorKeyword
from src.monitor import Monitor
from src.xianyu_ws import XianyuWebSocket
from src.reply_agent import ReplyAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger("main")

# 全局服务
monitor: Monitor | None = None
ws_client: XianyuWebSocket | None = None
reply_agent: ReplyAgent | None = None
cs_running = False


def _has_cookies() -> bool:
    return bool(config.XIANYU_COOKIES and config.XIANYU_COOKIES != "your_cookies_here")


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

    # 启动商品监控
    if _has_cookies():
        monitor = Monitor()
        monitor.start()
        logger.info("商品监控已启动")
    else:
        logger.warning("未配置 XIANYU_COOKIES，监控未启动")

    yield

    if monitor:
        await monitor.close()
    await _stop_cs()
    if reply_agent:
        await reply_agent.close()
    logger.info("服务已停止")


app = FastAPI(title="闲鱼 AI 智能助手", version="0.2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ==================== 通用 ====================

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "monitor_running": monitor is not None and monitor._running,
        "cs_running": cs_running,
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
        raise HTTPException(400, "监控未启动，请先配置 XIANYU_COOKIES")
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
        "interval_s": config.MONITOR_INTERVAL,
        "keywords": kw_list,
    }


# ==================== 智能客服 ====================

# 客服消息日志（内存）
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


async def _start_cs():
    global ws_client, cs_running
    if cs_running:
        return
    if not _has_cookies():
        raise HTTPException(400, "请先配置 XIANYU_COOKIES")

    ws_client = XianyuWebSocket(config.XIANYU_COOKIES)
    ws_client.on_message(_on_buyer_message)
    try:
        await ws_client.start()
        cs_running = True
        logger.info("智能客服已启动")
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


# ==================== 静态文件 ====================

@app.get("/")
async def index():
    return FileResponse(str(config.BASE_DIR / "frontend" / "dashboard.html"))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.main:app", host=config.HOST, port=config.PORT, reload=True)
