"""闲鱼 API 封装 — 基于 REST API + Cookie 认证"""
import hashlib
import time
import json
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
        """解析 cookie 字符串到 session（保持 URL 编码避免 httpx ASCII 错误）"""
        for part in self.cookies_str.split("; "):
            if "=" in part:
                key, val = part.split("=", 1)
                self.session.cookies.set(key, val, domain=".goofish.com")

    def _get_token(self) -> str:
        """从 cookie 中提取 _m_h5_tk 的 token 部分"""
        for part in self.cookies_str.split("; "):
            if part.startswith("_m_h5_tk="):
                val = part.split("=", 1)[1]
                return val.split("_")[0]
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

        API: mtop.taobao.idlemtopsearch.pc.search (2026年最新 PC 端)
        """
        t = str(int(time.time() * 1000))
        data_obj = {
            "pageNumber": page,
            "keyword": keyword,
            "fromFilter": False,
            "rowsPerPage": page_size,
            "sortValue": "",
            "sortField": "",
        }
        data_val = json.dumps(data_obj, ensure_ascii=False)

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
            "api": "mtop.taobao.idlemtopsearch.pc.search",
            "sessionOption": "AutoLoginOnly",
        }

        try:
            resp = await self.session.post(
                f"{self.BASE}/mtop.taobao.idlemtopsearch.pc.search/1.0/",
                params=params,
                data={"data": data_val},
            )
            text = resp.text
            if "FAIL_SYS" in text:
                return {"error": f"API不存在: {text[:200]}"}
            # httpx 可能返回 bytes，确保正确解码
            if isinstance(text, bytes):
                text = text.decode("utf-8")
            return json.loads(text)
        except Exception as e:
            return {"error": str(e)}

    async def get_item_detail(self, item_id: str) -> dict:
        """获取商品详情

        API: mtop.taobao.idle.pc.detail
        """
        t = str(int(time.time() * 1000))
        data_val = json.dumps({"itemId": item_id})

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

    @staticmethod
    def parse_search_results(data: dict, keyword: str) -> list:
        """解析搜索结果，提取商品列表（适配 2026 年闲鱼 API 响应结构）"""
        from src.models import XianyuItem

        items = []
        try:
            result = data.get("data", {})
            if isinstance(result, str):
                result = json.loads(result)

            # 新版 API: resultList 结构
            result_list = result.get("resultList", [])

            for raw in result_list:
                # 深嵌套提取
                item_data = raw.get("data", {})
                item_main = item_data.get("item", {}).get("main", {})
                args = item_main.get("clickParam", {}).get("args", {})
                ex_content = item_main.get("exContent", {})
                detail_params = ex_content.get("detailParams", {})

                item_id = str(args.get("id") or detail_params.get("itemId", ""))
                if not item_id:
                    continue

                # 价格
                price_str = str(args.get("price") or detail_params.get("soldPrice", "0"))
                try:
                    price = float(price_str)
                except ValueError:
                    price = 0.0

                # 标题（在 exContent 深层或 args.tag）
                title = str(detail_params.get("title") or args.get("tag", ""))
                # 清理换行
                title = title.replace("\\n", " ").replace("\n", " ").strip()

                # 卖家
                seller = str(detail_params.get("userNick") or args.get("seller_id", ""))
                if seller and len(seller) > 40:
                    # 可能是 base64，用 sellerId 的简写
                    seller = seller[:20] + "..."

                # 位置
                location = str(ex_content.get("area") or args.get("p_city", ""))

                # 图片（新版可能不在 args 里，暂用空）
                image_url = str(args.get("picUrl", ""))

                items.append(XianyuItem(
                    item_id=item_id,
                    title=title,
                    price=price,
                    seller=seller,
                    location=location,
                    image_url=image_url,
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
