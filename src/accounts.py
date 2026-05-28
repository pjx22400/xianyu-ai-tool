"""多账号管理 — 支持多个闲鱼账号切换

每个账号存储独立的 Cookie 和状态
"""
import json
import logging
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field
from src.config import config

logger = logging.getLogger("accounts")


class Account(BaseModel):
    """闲鱼账号"""
    id: str = Field(..., description="账号唯一标识")
    name: str = Field("", description="账号备注名")
    cookies: str = Field("", description="Cookie 字符串")
    enabled: bool = Field(True, description="是否启用")
    is_default: bool = Field(False, description="是否默认账号")


class AccountManager:
    """账号管理器"""

    FILE = config.DATA_DIR / "accounts.json"

    def __init__(self):
        self._accounts: dict[str, Account] = {}
        self._load()

    def _load(self):
        if self.FILE.exists():
            try:
                data = json.loads(self.FILE.read_text("utf-8"))
                for a in data:
                    acc = Account(**a)
                    self._accounts[acc.id] = acc
                logger.info(f"加载了 {len(self._accounts)} 个账号")
            except Exception as e:
                logger.error(f"加载账号文件失败: {e}")

    def _save(self):
        config.ensure_dirs()
        data = [a.model_dump() for a in self._accounts.values()]
        self.FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")

    def list(self) -> list[Account]:
        return list(self._accounts.values())

    def get(self, account_id: str) -> Optional[Account]:
        return self._accounts.get(account_id)

    def get_default(self) -> Optional[Account]:
        for a in self._accounts.values():
            if a.is_default and a.enabled and a.cookies:
                return a
        # 回退：第一个启用的有 Cookie 的账号
        for a in self._accounts.values():
            if a.enabled and a.cookies:
                return a
        return None

    def add(self, account: Account) -> bool:
        if account.id in self._accounts:
            return False
        if account.is_default:
            self._clear_defaults()
        self._accounts[account.id] = account
        self._save()
        return True

    def update(self, account_id: str, **kwargs) -> bool:
        if account_id not in self._accounts:
            return False
        a = self._accounts[account_id]
        for k, v in kwargs.items():
            if hasattr(a, k):
                setattr(a, k, v)
        if kwargs.get("is_default"):
            self._clear_defaults(except_id=account_id)
        self._save()
        return True

    def remove(self, account_id: str) -> bool:
        if account_id not in self._accounts:
            return False
        del self._accounts[account_id]
        self._save()
        return True

    def set_default(self, account_id: str) -> bool:
        """设为默认账号"""
        if account_id not in self._accounts:
            return False
        self._clear_defaults()
        self._accounts[account_id].is_default = True
        self._save()
        return True

    def _clear_defaults(self, except_id: str = ""):
        for a in self._accounts.values():
            if a.id != except_id:
                a.is_default = False

    @property
    def default_cookies(self) -> str:
        """获取默认账号的 Cookie（兼容 v0.2 配置）"""
        default = self.get_default()
        if default and default.cookies:
            return default.cookies
        return config.XIANYU_COOKIES  # 回退到 .env 中的旧配置


# 全局单例
account_manager = AccountManager()
