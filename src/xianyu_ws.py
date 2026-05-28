"""闲鱼 WebSocket 连接 — 实时消息收发

参考 XianyuAutoAgent 的实现，使用 wss-goofish.dingtalk.com
"""
import asyncio
import base64
import hashlib
import json
import logging
import random
import struct
import time
from typing import Optional, Callable, Awaitable

import httpx
import websockets

logger = logging.getLogger("xianyu_ws")


# ==================== 工具函数 ====================

def trans_cookies(cookies_str: str) -> dict:
    """解析 Cookie 字符串为字典"""
    result = {}
    for part in cookies_str.split("; "):
        if "=" in part:
            k, v = part.split("=", 1)
            result[k] = v
    return result


def generate_mid() -> str:
    return f"{int(1000 * random.random())}{int(time.time() * 1000)} 0"


def generate_uuid() -> str:
    return f"-{int(time.time() * 1000)}1"


def generate_device_id(user_id: str) -> str:
    chars = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    result = []
    for i in range(36):
        if i in (8, 13, 18, 23):
            result.append("-")
        elif i == 14:
            result.append("4")
        elif i == 19:
            result.append(chars[(int(16 * random.random()) & 0x3) | 0x8])
        else:
            result.append(chars[int(16 * random.random())])
    return "".join(result) + "-" + user_id


def generate_sign(t: str, token: str, data: str) -> str:
    app_key = "34839810"
    return hashlib.md5(f"{token}&{t}&{app_key}&{data}".encode()).hexdigest()


def decrypt_message(data: str) -> dict | None:
    """解密闲鱼消息 (Base64 → MessagePack → JSON)"""
    try:
        cleaned = "".join(c for c in data if c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
        while len(cleaned) % 4:
            cleaned += "="
        decoded = base64.b64decode(cleaned)
        decoder = _MsgPackDecoder(decoded)
        return decoder.decode()
    except Exception:
        return None


class _MsgPackDecoder:
    """MessagePack 解码器（精简版）"""
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def _read(self, n: int) -> bytes:
        r = self.data[self.pos:self.pos + n]
        self.pos += n
        return r

    def _u8(self): return self._read(1)[0]
    def _u16(self): return struct.unpack(">H", self._read(2))[0]
    def _u32(self): return struct.unpack(">I", self._read(4))[0]

    def decode(self):
        b = self._u8()
        if b <= 0x7f: return b
        if 0x80 <= b <= 0x8f: return self._map(b & 0x0f)
        if 0x90 <= b <= 0x9f: return self._array(b & 0x0f)
        if 0xa0 <= b <= 0xbf: return self._read(b & 0x1f).decode("utf-8")
        if b == 0xc0: return None
        if b == 0xc2: return False
        if b == 0xc3: return True
        if b == 0xc4: return self._read(self._u8())
        if b == 0xc5: return self._read(self._u16())
        if b == 0xc6: return self._read(self._u32())
        if b == 0xcc: return self._u8()
        if b == 0xcd: return self._u16()
        if b == 0xce: return self._u32()
        if b == 0xd9: return self._read(self._u8()).decode("utf-8")
        if b == 0xdc: return self._array(self._u16())
        if b == 0xde: return self._map(self._u16())
        if b >= 0xe0: return b - 256
        raise ValueError(f"Unknown format: 0x{b:02x}")

    def _array(self, n):
        return [self.decode() for _ in range(n)]

    def _map(self, n):
        return {self.decode(): self.decode() for _ in range(n)}


# ==================== 主类 ====================

Handler = Callable[[dict], Awaitable[None]]


class XianyuWebSocket:
    """闲鱼 WebSocket 实时消息客户端"""

    WSS_URL = "wss://wss-goofish.dingtalk.com/"
    APP_KEY = "444e9908a51d1cb236a27862abc769c9"
    UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36 "
        "DingTalk(2.1.5) OS(Windows/10) Browser(Chrome/133.0.0.0) DingWeb/2.1.5 IMPaaS DingWeb/2.1.5"
    )

    def __init__(self, cookies_str: str):
        self.cookies = trans_cookies(cookies_str)
        self.my_id = self.cookies.get("unb", "")
        self.device_id = generate_device_id(self.my_id)
        self._token: str | None = None
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._running = False
        self._handlers: list[Handler] = []
        self._order_handlers: list[Handler] = []
        self._http = httpx.AsyncClient(timeout=30)
        for k, v in self.cookies.items():
            self._http.cookies.set(k, v, domain=".goofish.com")

    # --- Token ---

    async def _get_token(self) -> str:
        """获取闲鱼 WebSocket Token"""
        t = str(int(time.time() * 1000))
        data_val = f'{{"appKey":"{self.APP_KEY}","deviceId":"{self.device_id}"}}'
        token_raw = self.cookies.get("_m_h5_tk", "").split("_")[0]
        sign = generate_sign(t, token_raw, data_val)

        try:
            resp = await self._http.post(
                "https://h5api.m.goofish.com/h5/mtop.taobao.idlemessage.pc.login.token/1.0/",
                params={
                    "jsv": "2.7.2", "appKey": "34839810", "t": t, "sign": sign,
                    "v": "1.0", "type": "originaljson", "accountSite": "xianyu",
                    "dataType": "json", "api": "mtop.taobao.idlemessage.pc.login.token",
                    "sessionOption": "AutoLoginOnly",
                },
                data={"data": data_val},
            )
            result = resp.json()
            raw_data = result.get("data", {})
            if isinstance(raw_data, str):
                raw_data = json.loads(raw_data)
            if "accessToken" in raw_data:
                return raw_data["accessToken"]
            ret = result.get("ret", [])
            raise RuntimeError(f"Token API异常: {ret}")
        except RuntimeError:
            raise
        except Exception as e:
            raise RuntimeError(f"获取 Token 失败: {e}")

    # --- 连接 ---

    async def connect(self):
        """建立 WebSocket 连接"""
        if not self._token:
            self._token = await self._get_token()
            logger.info("Token 获取成功")

        self._ws = await websockets.connect(self.WSS_URL)
        logger.info("WebSocket 已连接")

        # 注册
        await self._ws.send(json.dumps({
            "lwp": "/reg",
            "headers": {
                "cache-header": "app-key token ua wv",
                "app-key": self.APP_KEY,
                "token": self._token,
                "ua": self.UA,
                "dt": "j",
                "wv": "im:3,au:3,sy:6",
                "sync": "0,0;0;0;",
                "did": self.device_id,
                "mid": generate_mid(),
            },
        }))
        await asyncio.sleep(1)

        # 同步 ACK
        await self._ws.send(json.dumps({
            "lwp": "/r/SyncStatus/ackDiff",
            "headers": {"mid": generate_mid()},
            "body": [{
                "pipeline": "sync", "tooLong2Tag": "PNM,1",
                "channel": "sync", "topic": "sync",
                "highPts": 0, "pts": int(time.time() * 1000) * 1000,
                "seq": 0, "timestamp": int(time.time() * 1000),
            }],
        }))
        logger.info("连接注册完成 ✓")

    def on_message(self, handler: Handler):
        """注册消息处理器"""
        self._handlers.append(handler)

    def on_order(self, handler: Handler):
        """注册订单状态处理器"""
        self._order_handlers.append(handler)

    # --- 消息处理 ---

    @staticmethod
    def is_chat_message(msg: dict) -> bool:
        try:
            return (
                isinstance(msg, dict) and "1" in msg
                and isinstance(msg["1"], dict)
                and "10" in msg["1"]
                and isinstance(msg["1"]["10"], dict)
                and "reminderContent" in msg["1"]["10"]
            )
        except Exception:
            return False

    @staticmethod
    def is_sync_package(data: dict) -> bool:
        try:
            return (
                "body" in data
                and "syncPushPackage" in data["body"]
                and "data" in data["body"]["syncPushPackage"]
                and len(data["body"]["syncPushPackage"]["data"]) > 0
            )
        except Exception:
            return False

    @staticmethod
    def is_typing_status(msg: dict) -> bool:
        try:
            return (
                isinstance(msg, dict) and "1" in msg
                and isinstance(msg["1"], list) and len(msg["1"]) > 0
                and isinstance(msg["1"][0], dict)
                and "1" in msg["1"][0]
                and "@goofish" in str(msg["1"][0]["1"])
            )
        except Exception:
            return False

    @staticmethod
    def is_order_message(msg: dict) -> bool:
        """检测是否为订单状态变更消息（付款/发货/确认收货等）"""
        try:
            key_3 = msg.get("3") or msg.get("3", {})
            if isinstance(key_3, dict):
                red = key_3.get("redReminder")
                rtype = key_3.get("reminderType")
                if red and "等待" in str(red):
                    return True
                if rtype in ("WAIT_SELLER_SEND_GOODS", "WAIT_BUYER_PAY",
                             "WAIT_BUYER_CONFIRM_GOODS", "TRADE_CLOSED",
                             "TRADE_FINISHED", "SELLER_SEND_GOODS"):
                    return True
            return False
        except Exception:
            return False

    def extract_order_info(self, msg: dict) -> dict | None:
        try:
            key_3 = msg.get("3", {})
            return {
                "type": key_3.get("reminderType", "UNKNOWN"),
                "status": key_3.get("redReminder", ""),
                "order_id": key_3.get("orderId", ""),
                "item_title": key_3.get("reminderTitle", ""),
                "buyer_name": key_3.get("senderName", ""),
                "create_time": int(msg.get("1", {}).get("5", 0)),
            }
        except Exception:
            return None

    def extract_chat_info(self, msg: dict) -> dict | None:
        """从聊天消息中提取关键信息"""
        try:
            info = msg["1"]["10"]
            url = info.get("reminderUrl", "")
            item_id = url.split("itemId=")[1].split("&")[0] if "itemId=" in url else None
            chat_id = msg["1"]["2"].split("@")[0]

            return {
                "chat_id": chat_id,
                "item_id": item_id,
                "sender_name": info.get("reminderTitle", ""),
                "sender_id": info.get("senderUserId", ""),
                "content": info.get("reminderContent", ""),
                "create_time": int(msg["1"].get("5", 0)),
            }
        except Exception:
            return None

    async def send_reply(self, chat_id: str, to_id: str, text: str):
        """发送回复消息"""
        text_payload = json.dumps({"contentType": 1, "text": {"text": text}})
        text_b64 = base64.b64encode(text_payload.encode()).decode()

        msg = {
            "lwp": "/r/MessageSend/sendByReceiverScope",
            "headers": {"mid": generate_mid()},
            "body": [
                {
                    "uuid": generate_uuid(),
                    "cid": f"{chat_id}@goofish",
                    "conversationType": 1,
                    "content": {
                        "contentType": 101,
                        "custom": {"type": 1, "data": text_b64},
                    },
                    "redPointPolicy": 0,
                    "extension": {"extJson": "{}"},
                    "ctx": {"appVersion": "1.0", "platform": "web"},
                    "mtags": {},
                    "msgReadStatusSetting": 1,
                },
                {
                    "actualReceivers": [
                        f"{to_id}@goofish",
                        f"{self.my_id}@goofish",
                    ],
                },
            ],
        }
        await self._ws.send(json.dumps(msg))

    # --- 主循环 ---

    async def _listen_loop(self):
        """消息监听循环"""
        while self._running and self._ws:
            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=30)
            except asyncio.TimeoutError:
                continue

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue

            # 心跳 ACK
            try:
                ack = {
                    "code": 200,
                    "headers": {
                        "mid": data["headers"].get("mid", generate_mid()),
                        "sid": data["headers"].get("sid", ""),
                    },
                }
                for k in ("app-key", "ua", "dt"):
                    if k in data.get("headers", {}):
                        ack["headers"][k] = data["headers"][k]
                await self._ws.send(json.dumps(ack))
            except Exception:
                pass

            # 非同步包跳过
            if not self.is_sync_package(data):
                continue

            # 解密消息
            sync_data = data["body"]["syncPushPackage"]["data"][0]
            if "data" not in sync_data:
                continue

            decrypted = decrypt_message(sync_data["data"])
            if decrypted is None:
                # 尝试直接 base64 解码
                try:
                    raw_bytes = base64.b64decode(sync_data["data"])
                    decrypted = json.loads(raw_bytes.decode())
                except Exception:
                    continue

            # 过滤非聊天消息
            if self.is_typing_status(decrypted):
                continue

            # 订单状态消息 -> 分发给 order_handlers
            if self.is_order_message(decrypted):
                order_info = self.extract_order_info(decrypted)
                if order_info:
                    logger.info(f"📦 订单更新: {order_info['status']} [{order_info['item_title']}]")
                    for handler in self._order_handlers:
                        await handler(order_info)
                continue

            if not self.is_chat_message(decrypted):
                continue

            # 提取聊天信息并分发给处理器
            info = self.extract_chat_info(decrypted)
            if info is None:
                continue

            # 过滤过期消息（5分钟）
            if (time.time() * 1000 - info["create_time"]) > 300_000:
                continue

            # 忽略自己发的消息
            if info["sender_id"] == self.my_id:
                continue

            logger.info(
                f"📩 [{info['chat_id']}] {info['sender_name']}: {info['content'][:50]}"
            )

            for handler in self._handlers:
                await handler(info)

    # --- 生命周期 ---

    async def start(self):
        self._running = True
        await self.connect()
        asyncio.create_task(self._listen_loop())

    async def stop(self):
        self._running = False
        if self._ws:
            await self._ws.close()
        await self._http.aclose()
