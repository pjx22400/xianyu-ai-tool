"""闲鱼 API 封装 — 基于 REST API + Cookie 认证"""
import hashlib
import time
import re
from typing import Optional
from urllib.parse import urlencode
import httpx
from src.config import config


class XianyuAPI:
    """闲鱼 H5 API 客户端"""

    BASE = "https://h5api.m.goofish.com/h5"
    APP_KEY = "34839810"
    UA = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36"
    )

    def __init__(self, cookies_str: str = ""):
        self.cookies_str = cookies_str or config.XIANYU_COOKIES
        self.session = httpx.AsyncClient(
            headers={
                "User-Agent": self.UA,
                "Accept": "application/json",
                "Origin": "https://www.goofish.com",
                "Referer": "https://www.goofish.com/",
            },
            timeout=30,
        )
        self._parse_cookies()

    def _parse_cookies(self):
        """解析 cookie 字符串到 session"""
        for part in self.cookies_str.split("; "):
            if "=" in part:
                key, val = part.split("=", 1)
                self.session.cookies.set(key, val, domain=".goofish.com")

    def _get_token(self) -> str:
        """从 cookie 中提取 _m_h5_tk"""
        for cookie in self.session.cookies.jar:
            if cookie.name == "_m_h5_tk":
                return cookie.value.split("_")[0]
        return ""

    def _sign(self, t: str, data: str) -> str:
        """生成 API 签名: MD5(token&t&appKey&data)"""
        token = self._get_token()
        msg = f"{token}&{t}&{self.APP_KEY}&{data}"
        return hashlib.md5(msg.encode()).hexdigest()

    async def search(
        self,
        keyword: str,
        page: int = 1,
        page_size: int = 20,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
    ) -> dict:
        """搜索闲鱼商品

        API: mtop.taobao.idle.search.search
        """
        t = str(int(time.time() * 1000))
        data_val = (
            f'{{"keyword":"{keyword}","page":{page},"pageSize":{page_size},'
            f'"searchType":"standard","spm":"a21ybx.search.searchResult.1"}}'
        )

        params = {
            "jsv": "2.7.2",
            "appKey": self.APP_KEY,
            "t": t,
            "sign": self._sign(t, data_val),
            "v": "1.0",
            "type": "originaljson",
            "accountSite": "xianyu",
            "dataType": "json",
            "timeout": "20000",
            "api": "mtop.taobao.idle.search.search",
            "sessionOption": "AutoLoginOnly",
        }

        try:
            resp = await self.session.post(
                f"{self.BASE}/mtop.taobao.idle.search.search/1.0/",
                params=params,
                data={"data": data_val},
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    async def get_item_detail(self, item_id: str) -> dict:
        """获取商品详情

        API: mtop.taobao.idle.pc.detail
        """
        t = str(int(time.time() * 1000))
        data_val = f'{{"itemId":"{item_id}"}}'

        params = {
            "jsv": "2.7.2",
            "appKey": self.APP_KEY,
            "t": t,
            "sign": self._sign(t, data_val),
            "v": "1.0",
            "type": "originaljson",
            "accountSite": "xianyu",
            "dataType": "json",
            "timeout": "20000",
            "api": "mtop.taobao.idle.pc.detail",
            "sessionOption": "AutoLoginOnly",
        }

        try:
            resp = await self.session.post(
                f"{self.BASE}/mtop.taobao.idle.pc.detail/1.0/",
                params=params,
                data={"data": data_val},
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    def parse_search_results(self, data: dict, keyword: str) -> list:
        """解析搜索结果，提取商品列表"""
        from src.models import XianyuItem

        items = []
        try:
            # 闲鱼搜索 API 嵌套结构
            result = data.get("data", {})
            if isinstance(result, str):
                import json
                result = json.loads(result)

            item_list = result.get("itemList") or result.get("items") or []

            for raw in item_list:
                item_id = str(raw.get("itemId", ""))
                if not item_id:
                    continue

                price_str = str(raw.get("price", "0"))
                try:
                    price = float(price_str)
                except ValueError:
                    price = 0.0

                items.append(XianyuItem(
                    item_id=item_id,
                    title=str(raw.get("title", "")),
                    price=price,
                    seller=str(raw.get("sellerNick", raw.get("nick", ""))),
                    location=str(raw.get("ipLocation", raw.get("location", ""))),
                    image_url=str(raw.get("mainPic", raw.get("picUrl", ""))),
                    item_url=f"https://www.goofish.com/item?id={item_id}",
                    keyword=keyword,
                ))
        except Exception as e:
            print(f"[Parser] 解析搜索结果出错: {e}")

        return items

    async def check_login(self) -> bool:
        """检查登录状态是否有效"""
        try:
            resp = await self.session.get(
                "https://passport.goofish.com/newlogin/hasLogin.do",
                params={"appName": "xianyu", "fromSite": "77"},
            )
            data = resp.json()
            return data.get("content", {}).get("success", False)
        except Exception:
            return False

    async def close(self):
        await self.session.aclose()
