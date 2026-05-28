"""AI 回复引擎 — 意图分类 + DeepSeek 生成回复（v0.4 销售大脑版）

多 Agent 架构：
  classify → price / tech / shipping / greeting / other
  每个 Agent 内置销售心理学策略
"""

import logging
import os
import re
from typing import Optional
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("reply_agent")

# ==================== 提示词 v0.4 — 销售心理学 ====================

CLASSIFY_PROMPT = """你是闲鱼卖家的助手，分析买家消息意图。只回复类别名称：

- price: 砍价、问价、说贵了、问最低价、问能不能便宜、划算吗
- tech: 问参数、规格、型号、配置、使用说明、兼容性、功能
- shipping: 问发货、快递、自提、运费、什么时候发、多久到、包邮吗
- condition: 问成色、瑕疵、新旧、购买时间、保修、用了多久
- deal: 表示想买、要了、拍了、走什么平台、怎么交易、能留吗
- greeting: 打招呼、你好、在吗、还在吗、hi
- other: 其他

买家消息: {user_msg}
商品信息: {item_desc}

类别:"""

PRICE_PROMPT = """你是闲鱼卖家，买家在议价。你的目标是**促成成交**：

【议价策略】
1. 首次议价：先强调商品价值（成色好/稀缺/市场价参考），再给一个小让步（5-8%）
2. 二次议价：语气友善但坚守当前价位，用"已经是最低价了"+"很多人问"组合
3. 三次以上：坚定报价，可提到"再低我就自己留着了"，制造稀缺感

【成交技巧】
- 暗示有其他人也在问："刚才也有人想要，你确定要的话我先给你留着"
- 价格锚定："这个成色闲鱼上都卖XXX，我这个已经很实惠了"
- 小赠品策略："价格确实最低了，但我可以送你XX"

【底线】不要低于商品标价的 15%，语气诚恳但不卑微，不超过 100 字。

商品信息: {item_desc}
已议价 {bargain_count} 次
买家: {user_msg}
回复:"""

DEAL_PROMPT = """你是闲鱼卖家，买家表示想买。你的目标：**快速锁定成交**。

【策略】
1. 确认关键信息：成色/配件/发货方式
2. 给明确的下一步："你直接拍就行，我今天就能发"
3. 消除顾虑："有什么问题随时问，收到不满意退回来"
4. 轻微施压："那我就不给别人留了，你先拍"

友好热情，不超过 80 字。

商品信息: {item_desc}
买家: {user_msg}
回复:"""

GREETING_PROMPT = """你是闲鱼卖家，买家打招呼。你的目标：**引导进入购买对话**。

【策略】
1. 先确认商品还在："在的～"
2. 顺便提一个卖点："这个成色很好，买了基本没用过"
3. 开放性问题引导："有什么想了解的吗？"
4. 不超过 60 字，表情符号 1-2 个即可

商品信息: {item_desc}
买家: {user_msg}
回复:"""

SHIPPING_PROMPT = """你是闲鱼卖家，买家问物流。你的目标：**消除顾虑，促成交**。

【策略】
1. 明确回复快递/时间/包邮情况
2. 强调发货速度："今天下午就能发"
3. 顺带促单："现在拍的话，X天就能到"
4. 不超过 60 字

商品信息: {item_desc}
买家: {user_msg}
回复:"""

TECH_PROMPT = """你是闲鱼卖家，买家问技术细节。你的目标：**专业 + 促成交**。

【策略】
1. 准确回答核心问题
2. 不确定的说"我帮你查一下"，不要编
3. 回答后加一句引导："这个XX功能确实好用，买的人都说值"
4. 不超过 80 字

商品信息: {item_desc}
买家: {user_msg}
回复:"""

DEFAULT_PROMPT = """你是闲鱼卖家。友好回复，顺便推进成交。不超过 70 字。

商品信息: {item_desc}
买家: {user_msg}
回复:"""


# ==================== 辅助函数 ====================

def _safe_format(template: str, **kwargs) -> str:
    """安全模板替换 — 防止用户输入含 {} 炸异常"""
    result = template
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", str(value))
    return result


# ==================== Agent ====================

@dataclass
class Conversation:
    chat_id: str
    messages: list[dict] = field(default_factory=list)
    bargain_count: int = 0


@dataclass
class ReplyStats:
    """回复统计"""
    total: int = 0
    price: int = 0
    deal: int = 0
    greeting: int = 0
    tech: int = 0
    shipping: int = 0
    other: int = 0


class ReplyAgent:
    """AI 回复引擎 v0.4"""

    def __init__(
        self,
        api_key: str = "",
        base_url: str = "https://api.deepseek.com",
        model: str = "deepseek-chat",
    ):
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")
        self.base_url = base_url or os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.model = model
        self._conversations: dict[str, Conversation] = {}
        self.stats = ReplyStats()
        self._http = httpx.AsyncClient(
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30,
        )

    def get_or_create_conv(self, chat_id: str) -> Conversation:
        if chat_id not in self._conversations:
            self._conversations[chat_id] = Conversation(chat_id=chat_id)
        return self._conversations[chat_id]

    async def _call_llm(self, prompt: str, max_tokens: int = 200) -> str:
        try:
            resp = await self._http.post(
                f"{self.base_url}/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.75,
                },
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return "你好，商品还在的，有什么想问的可以直接说～"

    async def classify_intent(self, user_msg: str, item_desc: str) -> str:
        prompt = _safe_format(CLASSIFY_PROMPT, user_msg=user_msg, item_desc=item_desc)
        result = await self._call_llm(prompt, max_tokens=20)
        return result.strip().lower()

    async def generate_reply(
        self,
        user_msg: str,
        item_desc: str,
        chat_id: str,
        sender_id: str,
    ) -> str:
        """生成智能回复 — v0.4 销售大脑版"""
        conv = self.get_or_create_conv(chat_id)
        conv.messages.append({"role": "user", "content": user_msg})
        self.stats.total += 1

        text_clean = re.sub(r"[^\w\u4e00-\u9fa5]", "", user_msg)

        # === 快速意图匹配（关键词优先，减少 LLM 调用） ===

        # 1. 成交意图（最高优先级）
        deal_kw = ["要了", "拍了", "买了", "怎么拍", "如何交易", "走平台", "能留", "留给我",
                    "我要", "拿下", "收了", "怎么买", "下单", "付款"]
        if any(kw in text_clean for kw in deal_kw):
            self.stats.deal += 1
            prompt = _safe_format(DEAL_PROMPT, user_msg=user_msg, item_desc=item_desc)
            reply = await self._call_llm(prompt)
            conv.messages.append({"role": "assistant", "content": reply})
            return reply

        # 2. 砍价
        price_kw = ["便宜", "价", "砍价", "少点", "最低", "优惠", "贵", "降",
                     "刀", "小刀", "大刀", "能少", "可以少", "多少钱"]
        if any(kw in text_clean for kw in price_kw):
            conv.bargain_count += 1
            self.stats.price += 1
            prompt = _safe_format(
                PRICE_PROMPT,
                user_msg=user_msg, item_desc=item_desc, bargain_count=conv.bargain_count,
            )
            reply = await self._call_llm(prompt)
            conv.messages.append({"role": "assistant", "content": reply})
            return reply

        # 3. 打招呼
        greet_kw = ["你好", "在吗", "还在吗", "hi", "hello", "在不在", "老板"]
        if any(kw in text_clean for kw in greet_kw) and len(text_clean) < 10:
            self.stats.greeting += 1
            prompt = _safe_format(GREETING_PROMPT, user_msg=user_msg, item_desc=item_desc)
            reply = await self._call_llm(prompt)
            conv.messages.append({"role": "assistant", "content": reply})
            return reply

        # 4. 物流
        ship_kw = ["发货", "快递", "包邮", "运费", "自提", "什么时候", "多久到",
                    "什么快递", "发什么", "几天"]
        if any(kw in text_clean for kw in ship_kw):
            self.stats.shipping += 1
            prompt = _safe_format(SHIPPING_PROMPT, user_msg=user_msg, item_desc=item_desc)
            reply = await self._call_llm(prompt)
            conv.messages.append({"role": "assistant", "content": reply})
            return reply

        # 5. 技术
        tech_kw = ["参数", "规格", "型号", "配置", "兼容", "支持", "版本", "尺寸",
                    "内存", "硬盘", "电池", "屏幕", "处理器", "cpu"]
        if any(kw in text_clean for kw in tech_kw):
            self.stats.tech += 1
            prompt = _safe_format(TECH_PROMPT, user_msg=user_msg, item_desc=item_desc)
            reply = await self._call_llm(prompt)
            conv.messages.append({"role": "assistant", "content": reply})
            return reply

        # 6. LLM 兜底
        try:
            intent = await self.classify_intent(user_msg, item_desc)
        except Exception:
            intent = "other"

        if "price" in intent:
            conv.bargain_count += 1
            self.stats.price += 1
            prompt = _safe_format(PRICE_PROMPT, user_msg=user_msg, item_desc=item_desc,
                                   bargain_count=conv.bargain_count)
        elif "deal" in intent:
            self.stats.deal += 1
            prompt = _safe_format(DEAL_PROMPT, user_msg=user_msg, item_desc=item_desc)
        elif "shipping" in intent:
            self.stats.shipping += 1
            prompt = _safe_format(SHIPPING_PROMPT, user_msg=user_msg, item_desc=item_desc)
        elif "greeting" in intent:
            self.stats.greeting += 1
            prompt = _safe_format(GREETING_PROMPT, user_msg=user_msg, item_desc=item_desc)
        elif "tech" in intent:
            self.stats.tech += 1
            prompt = _safe_format(TECH_PROMPT, user_msg=user_msg, item_desc=item_desc)
        else:
            self.stats.other += 1
            prompt = _safe_format(DEFAULT_PROMPT, user_msg=user_msg, item_desc=item_desc)

        reply = await self._call_llm(prompt)
        conv.messages.append({"role": "assistant", "content": reply})
        return reply

    async def close(self):
        await self._http.aclose()
