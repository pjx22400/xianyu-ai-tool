"""pytest fixtures — 测试基础设施

提供:
  - 内存 SQLite 数据库（自动建表/清理）
  - 异步 HTTP 测试客户端
  - 认证辅助函数
"""

import asyncio
import os
import sys
import uuid
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# 确保项目根目录在 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 强制使用测试数据库路径
os.environ["DATA_DIR"] = "/tmp/xianyu_test_data"

from src.config import config
from src.database import init_db, close_db, get_db, DB_PATH, DEFAULT_USER_ID
from src.main import app
from src.auth import create_access_token, hash_password

# 重定向数据目录到临时位置
config.DATA_DIR = config.BASE_DIR / "tests" / "test_data"


@pytest.fixture(autouse=True)
def setup_test_env():
    """每个测试使用独立临时数据库"""
    import tempfile
    import src.database as db_module

    tmpdir = tempfile.mkdtemp(prefix="xianyu_test_")
    db_path = os.path.join(tmpdir, "test.db")

    # Patch DB_PATH
    original_path = db_module.DB_PATH
    db_module.DB_PATH = db_path
    db_module._db = None  # 重置连接

    yield

    # 清理
    asyncio.get_event_loop().run_until_complete(close_db())
    db_module.DB_PATH = original_path
    db_module._db = None
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest_asyncio.fixture
async def db():
    """初始化数据库并返回连接"""
    config.ensure_dirs()
    await init_db()
    db = await get_db()
    yield db
    await close_db()


@pytest_asyncio.fixture
async def client():
    """异步 HTTP 测试客户端"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def test_user():
    """测试用户数据"""
    uid = str(uuid.uuid4())
    return {
        "id": uid,
        "email": f"test_{uid[:8]}@example.com",
        "password": "testpass123",
        "tier": "free",
    }


@pytest.fixture
def auth_headers(test_user):
    """生成带 Authorization header 的字典"""
    token = create_access_token(test_user["id"], test_user["email"], test_user["tier"])
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def pro_user():
    """Pro 版用户"""
    uid = str(uuid.uuid4())
    return {
        "id": uid,
        "email": f"pro_{uid[:8]}@example.com",
        "password": "propass123",
        "tier": "pro",
    }


@pytest.fixture
def pro_auth_headers(pro_user):
    """Pro 版用户 token"""
    token = create_access_token(pro_user["id"], pro_user["email"], pro_user["tier"])
    return {"Authorization": f"Bearer {token}"}


# ==================== 辅助函数 ====================

async def register_user(client: AsyncClient, email: str, password: str = "testpass123") -> dict:
    """注册用户并返回响应 JSON"""
    r = await client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 200, f"注册失败: {r.text}"
    return r.json()


async def login_user(client: AsyncClient, email: str, password: str = "testpass123") -> dict:
    """登录并返回响应 JSON"""
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, f"登录失败: {r.text}"
    return r.json()


async def create_test_user_in_db(email: str, password: str, tier: str = "free") -> str:
    """直接在数据库创建用户，返回 user_id"""
    from src.database import create_user as db_create_user
    pw_hash = hash_password(password)
    return await db_create_user(email, pw_hash)
