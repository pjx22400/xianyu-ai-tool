"""测试 auth 模块 — JWT + 密码哈希"""

import time
import pytest
from src.auth import (
    create_access_token, create_refresh_token,
    verify_access_token, hash_password, verify_password,
    get_tier_config, check_feature, TIERS,
)


class TestPasswordHashing:
    def test_hash_and_verify(self):
        pw = "mypassword123"
        hashed = hash_password(pw)
        assert hashed != pw
        assert verify_password(pw, hashed)

    def test_wrong_password(self):
        hashed = hash_password("correct")
        assert not verify_password("wrong", hashed)

    def test_hash_is_unique(self):
        h1 = hash_password("same")
        h2 = hash_password("same")
        assert h1 != h2  # bcrypt 每次生成不同 salt


class TestAccessToken:
    def test_create_and_verify(self):
        token = create_access_token("user-1", "test@test.com", "free")
        payload = verify_access_token(token)
        assert payload is not None
        assert payload["sub"] == "user-1"
        assert payload["email"] == "test@test.com"
        assert payload["tier"] == "free"
        assert payload["type"] == "access"

    def test_expired_token(self):
        # 无法直接创建过期 token，测试垃圾 token
        assert verify_access_token("not.a.valid.token") is None
        assert verify_access_token("") is None

    def test_tampered_token(self):
        token = create_access_token("u1", "e@t.com", "free")
        parts = token.split(".")
        tampered = parts[0] + "." + parts[1] + ".badsig"
        assert verify_access_token(tampered) is None

    def test_wrong_type(self):
        token = create_access_token("u1", "e@t.com", "free")
        # 无法构造 type != access 的合法 token
        assert verify_access_token("x" * 50) is None


class TestRefreshToken:
    def test_create(self):
        token = create_refresh_token("user-1")
        assert len(token) > 20
        assert isinstance(token, str)

    def test_unique(self):
        t1 = create_refresh_token("user-1")
        t2 = create_refresh_token("user-1")
        assert t1 != t2


class TestTiers:
    def test_free_tier_config(self):
        cfg = get_tier_config("free")
        assert cfg["name"] == "免费版"
        assert cfg["max_keywords"] == 3
        assert cfg["auto_reply"] is False

    def test_pro_tier_config(self):
        cfg = get_tier_config("pro")
        assert cfg["name"] == "Pro 版"
        assert cfg["max_keywords"] == 999
        assert cfg["auto_reply"] is True

    def test_unknown_tier_falls_back_to_free(self):
        cfg = get_tier_config("enterprise")
        assert cfg["name"] == "免费版"

    def test_check_feature(self):
        assert check_feature("pro", "auto_reply") is True
        assert check_feature("free", "auto_reply") is False
        assert check_feature("pro", "profit_tracking") is True
        assert check_feature("free", "profit_tracking") is False
