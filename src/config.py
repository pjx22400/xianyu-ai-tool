"""配置管理 — 从环境变量和 .env 文件读取"""
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv(Path(__file__).parent.parent / ".env", override=True)


class Config:
    """全局配置"""

    # --- 项目路径 ---
    BASE_DIR = Path(__file__).parent.parent
    DATA_DIR = BASE_DIR / "data"
    STATE_FILE = DATA_DIR / "state.json"

    # --- 闲鱼 ---
    XIANYU_SEARCH_URL = "https://h5api.m.goofish.com/h5/mtop.taobao.idle.search.search/1.0/"
    XIANYU_ITEM_URL = "https://h5api.m.goofish.com/h5/mtop.taobao.idle.pc.detail/1.0/"
    XIANYU_APP_KEY = "34839810"
    XIANYU_COOKIES = os.getenv("XIANYU_COOKIES", "")

    # --- 监控 ---
    MONITOR_INTERVAL = int(os.getenv("MONITOR_INTERVAL", "300"))  # 扫描间隔（秒），默认 5 分钟
    MAX_ITEMS_PER_KEYWORD = int(os.getenv("MAX_ITEMS_PER_KEYWORD", "20"))

    # --- 数据库 ---
    DATABASE_URL = os.getenv("DATABASE_URL", f"sqlite+aiosqlite:///{DATA_DIR}/xianyu.db")

    # --- 飞书通知 ---
    FEISHU_APP_ID = os.getenv("FEISHU_APP_ID", "")
    FEISHU_APP_SECRET = os.getenv("FEISHU_APP_SECRET", "")
    FEISHU_USER_OPEN_ID = os.getenv("FEISHU_USER_OPEN_ID", "")

    # --- AI ---
    DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
    DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")

    # --- 服务 ---
    HOST = os.getenv("HOST", "0.0.0.0")
    PORT = int(os.getenv("PORT", "8000"))

    @classmethod
    def ensure_dirs(cls):
        """确保必要的目录存在"""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)


config = Config()
