"""监控核心 — 定时扫描 + 变化检测 + 通知"""
import asyncio
import logging
from datetime import datetime
from src.config import config
from src.database import get_keywords, upsert_items, get_items
from src.xianyu_api import XianyuAPI
from src.notifier import notify_new_items, notify_price_drops

logger = logging.getLogger("monitor")


class Monitor:
    """闲鱼商品监控器"""

    def __init__(self, cookies_str: str = ""):
        self.api = XianyuAPI(cookies_str)
        self._running = False
        self._task: asyncio.Task | None = None

    async def scan_keyword(self, keyword: str) -> dict:
        """扫描单个关键词，返回结果摘要"""
        try:
            resp = await self.api.search(keyword, page_size=config.MAX_ITEMS_PER_KEYWORD)
            if "error" in resp:
                return {"keyword": keyword, "error": resp["error"], "items": []}

            items = self.api.parse_search_results(resp, keyword)
            if not items:
                return {"keyword": keyword, "total": 0, "new": 0, "drops": 0, "items": []}

            # 存入数据库（自动检测新商品和降价）
            await upsert_items(keyword, items)

            # 从数据库取回带标记的结果
            saved_items = await get_items(keyword, limit=config.MAX_ITEMS_PER_KEYWORD)

            new_items = [it for it in saved_items if it.is_new]
            dropped_items = [it for it in saved_items if it.price_dropped]

            return {
                "keyword": keyword,
                "total": len(saved_items),
                "new": len(new_items),
                "drops": len(dropped_items),
                "items": saved_items,
                "new_items": [it.model_dump() for it in new_items],
                "dropped_items": [it.model_dump() for it in dropped_items],
            }
        except Exception as e:
            logger.error(f"扫描关键词 '{keyword}' 出错: {e}")
            return {"keyword": keyword, "error": str(e), "items": []}

    async def scan_all(self) -> list[dict]:
        """扫描所有启用的关键词"""
        keywords = await get_keywords(enabled_only=True)
        if not keywords:
            logger.info("没有启用的监控关键词")
            return []

        results = []
        total_new = 0
        total_drops = 0

        for kw in keywords:
            result = await self.scan_keyword(kw.keyword)
            results.append(result)
            total_new += result.get("new", 0)
            total_drops += result.get("drops", 0)

        # 发送通知
        all_new = []
        all_drops = []
        for r in results:
            all_new.extend(r.get("new_items", []))
            all_drops.extend(r.get("dropped_items", []))

        if all_new:
            await notify_new_items(all_new)
        if all_drops:
            await notify_price_drops(all_drops)

        logger.info(
            f"扫描完成: {len(keywords)} 个关键词, "
            f"新商品 {total_new}, 降价 {total_drops}"
        )
        return results

    async def run_loop(self):
        """持续监控循环"""
        self._running = True
        logger.info(f"监控启动，间隔 {config.MONITOR_INTERVAL}s")
        while self._running:
            try:
                await self.scan_all()
            except Exception as e:
                logger.error(f"监控循环出错: {e}")
            await asyncio.sleep(config.MONITOR_INTERVAL)

    def start(self):
        """启动监控（后台任务）"""
        if self._running:
            return
        self._task = asyncio.create_task(self.run_loop())

    def stop(self):
        """停止监控"""
        self._running = False
        if self._task:
            self._task.cancel()

    async def close(self):
        self.stop()
        await self.api.close()
