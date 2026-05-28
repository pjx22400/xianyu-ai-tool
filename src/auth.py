"""认证模块 — JWT + bcrypt + 用户管理

v0.5 SaaS: 多租户认证层
- 注册/登录/刷新令牌
- bcrypt 密码哈希
- JWT access token (15min) + refresh token (7d)
"""

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional

import bcrypt

logger = logging.getLogger("auth")

# JWT 签名密钥（生产环境应从环境变量读取）
_JWT_SECRET = os.getenv("JWT_SECRET", secrets.token_hex(32))
_REFRESH_SECRET = os.getenv("REFRESH_SECRET", secrets.token_hex(32))

ACCESS_TOKEN_TTL = 15 * 60        # 15 分钟
REFRESH_TOKEN_TTL = 7 * 24 * 3600  # 7 天


# ==================== JWT ====================

def _b64url_encode(data: bytes) -> str:
    import base64
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    import base64
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def create_access_token(user_id: str, email: str, tier: str) -> str:
    """生成 JWT access token"""
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps({
        "sub": user_id,
        "email": email,
        "tier": tier,
        "iat": int(time.time()),
        "exp": int(time.time()) + ACCESS_TOKEN_TTL,
        "type": "access",
    }).encode())
    signature = _b64url_encode(
        hmac.new(_JWT_SECRET.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest()
    )
    return f"{header}.{payload}.{signature}"


def create_refresh_token(user_id: str) -> str:
    """生成 refresh token（不存 payload，存 DB）"""
    token = secrets.token_urlsafe(48)
    return token


def verify_access_token(token: str) -> Optional[dict]:
    """验证 JWT，返回 payload 或 None"""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        header_b64, payload_b64, sig_b64 = parts

        # 验证签名
        expected_sig = _b64url_encode(
            hmac.new(_JWT_SECRET.encode(),
                     f"{header_b64}.{payload_b64}".encode(),
                     hashlib.sha256).digest()
        )
        if not hmac.compare_digest(sig_b64, expected_sig):
            return None

        payload = json.loads(_b64url_decode(payload_b64))

        # 检查过期
        if payload.get("exp", 0) < time.time():
            return None

        # 检查类型
        if payload.get("type") != "access":
            return None

        return payload
    except Exception:
        return None


# ==================== 密码 ====================

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# ==================== 订阅 ====================

TIERS = {
    "free": {
        "name": "免费版",
        "max_keywords": 3,
        "max_accounts": 1,
        "auto_reply": False,
        "auto_refresh": False,
        "profit_tracking": False,
        "refresh_interval_min": 1440,  # 24h
        "rate_limit_per_min": 30,
    },
    "pro": {
        "name": "Pro 版",
        "max_keywords": 999,
        "max_accounts": 10,
        "auto_reply": True,
        "auto_refresh": True,
        "profit_tracking": True,
        "refresh_interval_min": 60,  # 1h
        "rate_limit_per_min": 300,
    },
}

PRICE_MONTHLY = 29   # ¥29/月
PRICE_YEARLY = 199   # ¥199/年


def get_tier_config(tier: str) -> dict:
    return TIERS.get(tier, TIERS["free"])


def check_feature(tier: str, feature: str) -> bool:
    """检查订阅是否有某功能"""
    config = get_tier_config(tier)
    return config.get(feature, False)
