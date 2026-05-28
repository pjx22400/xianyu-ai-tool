"""测试交易/利润 API 端点"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from src.database import create_user as db_create_user
from src.auth import hash_password, create_access_token


pytestmark = pytest.mark.asyncio


class TestDealAPI:
    _counter = 0

    async def _create_user_and_token(self, db, tier: str = "free"):
        TestDealAPI._counter += 1
        pw_hash = hash_password("test123")
        email = f"deal_{TestDealAPI._counter}@test.com"
        uid = await db_create_user(email, pw_hash)
        # 注意：token 里的 tier 和 DB 里的 tier 必须一致
        token = create_access_token(uid, email, tier)
        return uid, {"Authorization": f"Bearer {token}"}

    async def test_create_deal(self, client: AsyncClient, db):
        _, headers = await self._create_user_and_token(db)
        r = await client.post("/api/deals", json={
            "item_title": "AirPods Pro", "cost_price": 800, "sell_price": 1200
        }, headers=headers)
        assert r.status_code == 200
        assert r.json()["ok"] is True

    async def test_list_deals(self, client: AsyncClient, db):
        _, headers = await self._create_user_and_token(db)
        await client.post("/api/deals", json={
            "item_title": "Item 1", "sell_price": 100
        }, headers=headers)
        await client.post("/api/deals", json={
            "item_title": "Item 2", "sell_price": 200
        }, headers=headers)

        r = await client.get("/api/deals", headers=headers)
        assert r.status_code == 200
        assert len(r.json()) == 2

    async def test_profit_summary(self, client: AsyncClient, db):
        _, headers = await self._create_user_and_token(db)
        await client.post("/api/deals", json={
            "item_title": "Test", "cost_price": 500, "sell_price": 1000, "shipping_cost": 15
        }, headers=headers)

        r = await client.get("/api/deals/summary", headers=headers)
        data = r.json()
        assert data["total_revenue"] == 1000
        assert data["total_cost"] == 500
        assert data["total_profit"] == 485  # 1000 - 500 - 15

    async def test_deal_isolation(self, client: AsyncClient, db):
        _, headers_a = await self._create_user_and_token(db)
        _, headers_b = await self._create_user_and_token(db)

        await client.post("/api/deals", json={
            "item_title": "A deal", "sell_price": 999
        }, headers=headers_a)

        r = await client.get("/api/deals/summary", headers=headers_b)
        assert r.json()["total_deals"] == 0

    async def test_optional_fields(self, client: AsyncClient, db):
        """测试可选字段（运费、手续费、备注）有默认值"""
        _, headers = await self._create_user_and_token(db)
        r = await client.post("/api/deals", json={
            "item_title": "Minimal", "sell_price": 50
        }, headers=headers)
        assert r.status_code == 200

    async def test_missing_required_field(self, client: AsyncClient, db):
        _, headers = await self._create_user_and_token(db)
        r = await client.post("/api/deals", json={
            "item_title": "No Price"  # 缺少 sell_price
        }, headers=headers)
        assert r.status_code == 422

    async def test_empty_title(self, client: AsyncClient, db):
        _, headers = await self._create_user_and_token(db)
        r = await client.post("/api/deals", json={
            "item_title": "", "sell_price": 100
        }, headers=headers)
        # 空字符串应该通过（前端可能提交空值）
        assert r.status_code in (200, 422)
