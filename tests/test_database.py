"""测试 database 模块 — CRUD 操作"""

import uuid
import pytest
import pytest_asyncio
from src.database import (
    create_user, get_user_by_email, get_user_by_id, get_all_users,
    save_refresh_token, verify_refresh_token, revoke_refresh_token,
    add_keyword, get_keywords, count_keywords, delete_keyword, toggle_keyword,
    add_deal, get_deals, get_profit_summary,
    get_platform_stats,
)
from src.models import MonitorKeyword
from src.auth import create_refresh_token as make_refresh
from datetime import datetime, timedelta


pytestmark = pytest.mark.asyncio


class TestUserCRUD:
    async def test_create_user(self, db):
        uid = await create_user("test@test.com", "hash123")
        assert uid is not None
        assert len(uid) == 36  # UUID

    async def test_get_user_by_email(self, db):
        await create_user("findme@test.com", "hash")
        user = await get_user_by_email("findme@test.com")
        assert user is not None
        assert user["email"] == "findme@test.com"
        assert user["tier"] == "free"

    async def test_get_nonexistent_user(self, db):
        user = await get_user_by_email("nobody@test.com")
        assert user is None

    async def test_get_user_by_id(self, db):
        uid = await create_user("idtest@test.com", "hash")
        user = await get_user_by_id(uid)
        assert user["id"] == uid

    async def test_duplicate_email(self, db):
        await create_user("dup@test.com", "hash1")
        with pytest.raises(Exception):
            await create_user("dup@test.com", "hash2")

    async def test_get_all_users(self, db):
        await create_user("a@test.com", "h1")
        await create_user("b@test.com", "h2")
        users = await get_all_users()
        assert len(users) >= 2


class TestRefreshToken:
    async def test_save_and_verify(self, db):
        uid = await create_user("rt@test.com", "hash")
        token = make_refresh(uid)
        expires = (datetime.utcnow() + timedelta(days=7)).isoformat()
        await save_refresh_token(uid, token, expires)

        result = await verify_refresh_token(token)
        assert result == uid

    async def test_invalid_token(self, db):
        result = await verify_refresh_token("invalid_token")
        assert result is None

    async def test_revoke(self, db):
        uid = await create_user("revoke@test.com", "hash")
        token = make_refresh(uid)
        expires = (datetime.utcnow() + timedelta(days=7)).isoformat()
        await save_refresh_token(uid, token, expires)

        await revoke_refresh_token(token)
        result = await verify_refresh_token(token)
        assert result is None


class TestKeywordCRUD:
    async def test_add_and_list(self, db):
        uid = await create_user("kw@test.com", "hash")
        kw = MonitorKeyword(keyword="iPhone 15", max_price=5000)
        await add_keyword(kw, uid)

        keywords = await get_keywords(uid)
        assert len(keywords) == 1
        assert keywords[0].keyword == "iPhone 15"

    async def test_count(self, db):
        uid = await create_user("count@test.com", "hash")
        assert await count_keywords(uid) == 0
        await add_keyword(MonitorKeyword(keyword="k1"), uid)
        await add_keyword(MonitorKeyword(keyword="k2"), uid)
        assert await count_keywords(uid) == 2

    async def test_toggle(self, db):
        uid = await create_user("toggle@test.com", "hash")
        await add_keyword(MonitorKeyword(keyword="t1"), uid)
        await toggle_keyword("t1", False, uid)
        keywords = await get_keywords(uid, enabled_only=True)
        assert len(keywords) == 0

    async def test_delete(self, db):
        uid = await create_user("del@test.com", "hash")
        await add_keyword(MonitorKeyword(keyword="d1"), uid)
        await delete_keyword("d1", uid)
        keywords = await get_keywords(uid)
        assert len(keywords) == 0

    async def test_user_isolation(self, db):
        uid_a = await create_user("a@test.com", "h")
        uid_b = await create_user("b@test.com", "h")
        await add_keyword(MonitorKeyword(keyword="a_only"), uid_a)

        assert len(await get_keywords(uid_a)) == 1
        assert len(await get_keywords(uid_b)) == 0


class TestDealCRUD:
    async def test_add_deal(self, db):
        uid = await create_user("deal@test.com", "hash")
        deal_id = await add_deal(uid, "AirPods", sell_price=1200, cost_price=800)
        assert deal_id is not None

    async def test_get_deals(self, db):
        uid = await create_user("deals@test.com", "hash")
        await add_deal(uid, "Item1", sell_price=100, cost_price=50)
        await add_deal(uid, "Item2", sell_price=200, cost_price=150)
        deals = await get_deals(uid)
        assert len(deals) == 2

    async def test_profit_summary(self, db):
        uid = await create_user("profit@test.com", "hash")
        await add_deal(uid, "Item", sell_price=1000, cost_price=600, shipping_cost=20)
        summary = await get_profit_summary(uid)
        assert summary["total_revenue"] == 1000
        assert summary["total_profit"] == 380  # 1000 - 600 - 20
        assert summary["profit_margin"] == 38.0

    async def test_deal_isolation(self, db):
        uid_a = await create_user("da@test.com", "h")
        uid_b = await create_user("db@test.com", "h")
        await add_deal(uid_a, "A only", sell_price=100)
        assert (await get_profit_summary(uid_b))["total_deals"] == 0


class TestPlatformStats:
    async def test_stats(self, db):
        await create_user("s1@test.com", "h")
        await create_user("s2@test.com", "h")
        stats = await get_platform_stats()
        assert stats["total_users"] >= 2
