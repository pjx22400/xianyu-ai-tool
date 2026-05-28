"""测试认证 API 端点"""

import pytest
import pytest_asyncio
from httpx import AsyncClient
from src.database import create_user as db_create_user
from src.auth import hash_password


pytestmark = pytest.mark.asyncio


class TestRegister:
    async def test_register_success(self, client: AsyncClient, db):
        r = await client.post("/api/auth/register", json={
            "email": "newuser@test.com", "password": "testpass123"
        })
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["user"]["tier"] == "free"
        assert data["user"]["email"] == "newuser@test.com"

    async def test_register_duplicate(self, client: AsyncClient, db):
        await client.post("/api/auth/register", json={
            "email": "dup@test.com", "password": "testpass123"
        })
        r = await client.post("/api/auth/register", json={
            "email": "dup@test.com", "password": "testpass123"
        })
        assert r.status_code == 400

    async def test_register_short_password(self, client: AsyncClient, db):
        r = await client.post("/api/auth/register", json={
            "email": "short@test.com", "password": "12345"
        })
        assert r.status_code == 422  # Pydantic validation

    async def test_register_missing_email(self, client: AsyncClient, db):
        r = await client.post("/api/auth/register", json={"password": "test123456"})
        assert r.status_code == 422


class TestLogin:
    async def test_login_success(self, client: AsyncClient, db):
        # 先创建用户
        pw_hash = hash_password("mypassword")
        uid = await db_create_user("login_test@test.com", pw_hash)

        r = await client.post("/api/auth/login", json={
            "email": "login_test@test.com", "password": "mypassword"
        })
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert data["user"]["email"] == "login_test@test.com"

    async def test_login_wrong_password(self, client: AsyncClient, db):
        pw_hash = hash_password("correct")
        await db_create_user("wrongpw@test.com", pw_hash)

        r = await client.post("/api/auth/login", json={
            "email": "wrongpw@test.com", "password": "wrong_password"
        })
        assert r.status_code == 401

    async def test_login_nonexistent_user(self, client: AsyncClient, db):
        r = await client.post("/api/auth/login", json={
            "email": "nobody@test.com", "password": "whatever"
        })
        assert r.status_code == 401


class TestMe:
    async def test_me_with_valid_token(self, client: AsyncClient, db):
        pw_hash = hash_password("pass")
        uid = await db_create_user("me_test@test.com", pw_hash)
        r = await client.post("/api/auth/login", json={
            "email": "me_test@test.com", "password": "pass"
        })
        token = r.json()["access_token"]

        r = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == "me_test@test.com"
        assert data["tier_name"] == "免费版"

    async def test_me_without_token(self, client: AsyncClient, db):
        r = await client.get("/api/auth/me")
        assert r.status_code == 401

    async def test_me_with_bad_token(self, client: AsyncClient, db):
        r = await client.get("/api/auth/me", headers={"Authorization": "Bearer badtoken"})
        assert r.status_code == 401


class TestRefresh:
    async def test_refresh_success(self, client: AsyncClient, db):
        pw_hash = hash_password("pass")
        uid = await db_create_user("refresh_test@test.com", pw_hash)
        r = await client.post("/api/auth/login", json={
            "email": "refresh_test@test.com", "password": "pass"
        })
        refresh_token = r.json()["refresh_token"]

        r = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert r.status_code == 200
        data = r.json()
        assert "access_token" in data
        assert "refresh_token" in data  # 新 refresh token

    async def test_refresh_with_used_token(self, client: AsyncClient, db):
        pw_hash = hash_password("pass")
        await db_create_user("rt2@test.com", pw_hash)
        r = await client.post("/api/auth/login", json={
            "email": "rt2@test.com", "password": "pass"
        })
        refresh_token = r.json()["refresh_token"]

        # 第一次刷新
        await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        # 第二次用同一个 token
        r = await client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert r.status_code == 401
