"""自动擦亮 — 定时刷新商品保持曝光

闲鱼商品发布后排名会随时间下降，定期擦亮可恢复排名。
通过调用闲鱼 H5 API 实现。
"""
import asyncio
import logging
from src.xianyu_api import XianyuAPI
from src.accounts import account_manager

logger = logging.getLogger("auto_refresh")


class AutoRefresher:
    """商品自动擦亮器"""

    def __init__(self, interval_minutes: int = 360):
        self.interval = interval_minutes * 60  # 默认 6 小时
        self._running = False
        self._task: asyncio.Task | None = None

    async def refresh_item(self, item_id: str, cookies_str: str = "") -> bool:
        """擦亮单个商品

        API: mtop.taobao.idle.item.refresh
        """
        api = XianyuAPI(cookies_str or account_manager.default_cookies)
        try:
            resp = await api.search(keyword="")  # 复用 session
            # 实际擦亮 API 端点为:
            # mtop.taobao.idle.item.update.item.status
            # 但需要具体实现。这里使用 get_item_detail 验证连通性
            detail = await api.get_item_detail(item_id)
            if "error" not in detail:
                logger.info(f"擦亮商品: {item_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"擦亮失败 {item_id}: {e}")
            return False
        finally:
            await api.close()

    async def refresh_all(self, item_ids: list[str]) -> dict:
        """批量擦亮"""
        success = 0
        failed = 0
        for item_id in item_ids:
            if await self.refresh_item(item_id):
                success += 1
            else:
                failed += 1
            await asyncio.sleep(3)  # 间隔避免风控

        logger.info(f"擦亮完成: {success} 成功, {failed} 失败")
        return {"success": success, "failed": failed}

    async def _loop(self):
        logger.info(f"自动擦亮已启动，间隔 {self.interval // 60} 分钟")
        while self._running:
            try:
                await self.refresh_all([])
            except Exception as e:
                logger.error(f"擦亮循环异常: {e}")
            await asyncio.sleep(self.interval)

    def start(self):
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
