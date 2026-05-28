"""AI 回复引擎 — 意图分类 + DeepSeek 生成回复

多 Agent 架构（参考 XianyuAutoAgent）：
  classify → 识别意图 → price / tech / default Agent 各司其职
"""
import logging
import os
import re
from typing import Optional
from dataclasses import dataclass, field

import httpx

logger = logging.getLogger("reply_agent")

# ==================== 提示词 ====================

CLASSIFY_PROMPT = """你是闲鱼卖家的助手，负责分析买家消息的意图。
请从以下类别中选择最匹配的一个，只回复类别名称：

- price: 砍价、问价格、说贵了、问最低价、问能否便宜
- tech: 问参数、规格、型号、配置、使用说明、兼容性
- shipping: 问发货、快递、自提、运费、发货时间
- condition: 问成色、瑕疵、新旧、购买时间、保修
- greeting: 打招呼、你好、在吗、还在吗
- other: 其他问题

买家消息: {user_msg}
商品信息: {item_desc}

类别:"""

PRICE_PROMPT = """你是闲鱼卖家。买家在议价，你需要：
1. 礼貌但不轻易降价
2. 如果是首次议价，可以小幅降价（5-10%）
3. 如果已经多次议价，坚持当前价格
4. 强调商品价值而非只是价格
5. 不超过 80 字

商品信息: {item_desc}
议价次数: {bargain_count}
买家: {user_msg}
回复:"""

TECH_PROMPT = """你是闲鱼卖家，买家在询问商品技术细节。请：
1. 准确回答，不确定的说"建议查官网"
2. 友好专业，不超过 100 字

商品信息: {item_desc}
买家: {user_msg}
回复:"""

DEFAULT_PROMPT = """你是闲鱼卖家。请友好简洁回复买家，不超过 80 字。

商品信息: {item_desc}
买家: {user_msg}
回复:"""

# ==================== Agent ====================

@dataclass
class Conversation:
    chat_id: str
    messages: list[dict] = field(default_factory=list)
    bargain_count: int = 0


class ReplyAgent:
    """AI 回复引擎"""

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
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=30,
        )

    def get_or_create_conv(self, chat_id: str) -> Conversation:
        if chat_id not in self._conversations:
            self._conversations[chat_id] = Conversation(chat_id=chat_id)
        return self._conversations[chat_id]

    async def _call_llm(self, prompt: str, max_tokens: int = 150) -> str:
        """调用 DeepSeek API"""
        if not self.api_key:
            return "（未配置 API Key，使用默认回复）你好，商品还在，有什么想问的？"

        try:
            resp = await self._http.post(
                "/v1/chat/completions",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": max_tokens,
                    "temperature": 0.7,
                },
            )
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return "你好，商品还在的，有什么想问的可以直接说～"

    async def classify_intent(self, user_msg: str, item_desc: str) -> str:
        """识别买家意图"""
        prompt = CLASSIFY_PROMPT.format(user_msg=user_msg, item_desc=item_desc)
        result = await self._call_llm(prompt, max_tokens=20)
        return result.strip().lower()

    async def generate_reply(
        self,
        user_msg: str,
        item_desc: str,
        chat_id: str,
        sender_id: str,
    ) -> str:
        """生成智能回复"""
        conv = self.get_or_create_conv(chat_id)
        conv.messages.append({"role": "user", "content": user_msg})

        # 快速规则预判
        text_clean = re.sub(r"[^\w\u4e00-\u9fa5]", "", user_msg)

        # 1. 砍价关键词快速匹配
        price_kw = ["便宜", "价", "砍价", "少点", "最低", "优惠", "贵", "降"]
        if any(kw in text_clean for kw in price_kw):
            conv.bargain_count += 1
            prompt = PRICE_PROMPT.format(
                user_msg=user_msg, item_desc=item_desc, bargain_count=conv.bargain_count
            )
            reply = await self._call_llm(prompt)
            conv.messages.append({"role": "assistant", "content": reply})
            return reply

        # 2. 技术类关键词
        tech_kw = ["参数", "规格", "型号", "配置", "兼容", "支持", "版本", "尺寸"]
        if any(kw in text_clean for kw in tech_kw):
            prompt = TECH_PROMPT.format(user_msg=user_msg, item_desc=item_desc)
            reply = await self._call_llm(prompt)
            conv.messages.append({"role": "assistant", "content": reply})
            return reply

        # 3. 大模型兜底分类
        intent = await self.classify_intent(user_msg, item_desc)

        if "price" in intent:
            conv.bargain_count += 1
            prompt = PRICE_PROMPT.format(
                user_msg=user_msg, item_desc=item_desc, bargain_count=conv.bargain_count
            )
        elif "tech" in intent:
            prompt = TECH_PROMPT.format(user_msg=user_msg, item_desc=item_desc)
        else:
            prompt = DEFAULT_PROMPT.format(user_msg=user_msg, item_desc=item_desc)

        reply = await self._call_llm(prompt)
        conv.messages.append({"role": "assistant", "content": reply})
        return reply

    async def close(self):
        await self._http.aclose()
