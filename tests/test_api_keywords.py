"""测试关键词 API 端点"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from src.database import create_user as db_create_user
from src.auth import hash_password, create_access_token


pytestmark = pytest.mark.asyncio


class TestKeywordAPI:
    _counter = 0

    async def _create_user_and_token(self, client: AsyncClient, db, tier: str = "free"):
        TestKeywordAPI._counter += 1
        pw_hash = hash_password("test123")
        email = f"kw_{TestKeywordAPI._counter}@test.com"
        uid = await db_create_user(email, pw_hash)
        token = create_access_token(uid, email, tier)
        return uid, {"Authorization": f"Bearer {token}"}

    async def test_add_keyword(self, client: AsyncClient, db):
        uid, headers = await self._create_user_and_token(client, db)
        r = await client.post("/api/keywords", json={"keyword": "iPhone 16"}, headers=headers)
        assert r.status_code == 200

        r = await client.get("/api/keywords", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 1

    async def test_tier_limit_free(self, client: AsyncClient, db):
        uid, headers = await self._create_user_and_token(client, db, "free")
        for i in range(3):
            r = await client.post("/api/keywords", json={"keyword": f"kw{i}"}, headers=headers)
            assert r.status_code == 200, f"第 {i+1} 个关键词失败: {r.text}"

        # 第 4 个应被拒
        r = await client.post("/api/keywords", json={"keyword": "超额"}, headers=headers)
        assert r.status_code == 403, f"应返回 403，实际: {r.status_code} {r.text}"

    async def test_tier_limit_pro(self, client: AsyncClient, db):
        _, headers = await self._create_user_and_token(client, db, "pro")
        # 覆盖：直接在 DB 创建 pro 用户
        from src.database import create_user as db_create_user_raw
        pw_hash = hash_password("protest")
        uid = await db_create_user_raw("pro_kw_limit@test.com", pw_hash, tier="pro")
        token = create_access_token(uid, "pro_kw_limit@test.com", "pro")
        headers = {"Authorization": f"Bearer {token}"}
        for i in range(5):
            r = await client.post("/api/keywords", json={"keyword": f"pro_kw{i}"}, headers=headers)
            assert r.status_code == 200, f"Pro 用户第 {i+1} 个关键词失败: {r.text}"

    async def test_delete_keyword(self, client: AsyncClient, db):
        uid, headers = await self._create_user_and_token(client, db)
        await client.post("/api/keywords", json={"keyword": "to_delete"}, headers=headers)
        r = await client.delete("/api/keywords/to_delete", headers=headers)
        assert r.status_code == 200

        r = await client.get("/api/keywords", headers=headers)
        assert len(r.json()) == 0

    async def test_toggle_keyword(self, client: AsyncClient, db):
        uid, headers = await self._create_user_and_token(client, db)
        await client.post("/api/keywords", json={"keyword": "toggle_me"}, headers=headers)

        r = await client.put("/api/keywords/toggle_me/toggle?enabled=false", headers=headers)
        assert r.status_code == 200

    async def test_user_isolation(self, client: AsyncClient, db):
        uid_a, headers_a = await self._create_user_and_token(client, db)
        uid_b, headers_b = await self._create_user_and_token(client, db)

        await client.post("/api/keywords", json={"keyword": "a_only"}, headers=headers_a)
        r = await client.get("/api/keywords", headers=headers_b)
        assert len(r.json()) == 0

    async def test_require_auth_for_create(self, client: AsyncClient, db):
        r = await client.post("/api/keywords", json={"keyword": "no_auth"})
        assert r.status_code == 401

    async def test_list_without_auth(self, client: AsyncClient, db):
        r = await client.get("/api/keywords")
        assert r.status_code == 200  # 向后兼容，无 token 用默认用户
