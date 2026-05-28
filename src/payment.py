"""支付模块 — 订单管理 + Mock/真实支付 v0.6

支持:
  - Mock 模式（开发/测试）：一键支付成功
  - 真实模式（生产）：支付宝/微信扫码支付

订单生命周期:
  pending → paid → activated
"""

import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger("payment")


@dataclass
class Order:
    id: str
    user_id: str
    amount: float
    plan: str  # "pro_monthly" | "pro_yearly"
    status: str = "pending"  # pending | paid | activated | expired | cancelled
    payment_method: str = "mock"
    created_at: float = field(default_factory=time.time)
    paid_at: Optional[float] = None


# 价格表（元）
PLANS = {
    "pro_monthly": {"name": "Pro 月度", "price": 29.0, "days": 30, "tier": "pro"},
    "pro_yearly": {"name": "Pro 年度", "price": 199.0, "days": 365, "tier": "pro"},
}

# 订单过期时间（秒）
ORDER_EXPIRE_SECONDS = 1800  # 30 分钟


class PaymentService:
    """支付服务 — 单例"""

    _instance: Optional["PaymentService"] = None

    def __init__(self, mode: str = "mock"):
        self.mode = mode  # "mock" | "alipay" | "wechat"
        self._orders: dict[str, Order] = {}

    @classmethod
    def get(cls, mode: str = "mock") -> "PaymentService":
        if cls._instance is None:
            cls._instance = cls(mode=mode)
        return cls._instance

    def create_order(self, user_id: str, plan: str) -> Order | None:
        """创建支付订单"""
        if plan not in PLANS:
            return None
        info = PLANS[plan]
        order = Order(
            id=str(uuid.uuid4())[:12],
            user_id=user_id,
            amount=info["price"],
            plan=plan,
        )
        self._orders[order.id] = order
        logger.info(f"订单创建: {order.id} · {info['name']} · ¥{info['price']}")
        return order

    def get_order(self, order_id: str) -> Order | None:
        return self._orders.get(order_id)

    def mock_pay(self, order_id: str) -> Order | None:
        """Mock 支付（开发用）"""
        order = self._orders.get(order_id)
        if not order:
            return None
        if order.status != "pending":
            return None
        if time.time() - order.created_at > ORDER_EXPIRE_SECONDS:
            order.status = "expired"
            return None
        order.status = "paid"
        order.paid_at = time.time()
        logger.info(f"Mock 支付成功: {order.id} · ¥{order.amount}")
        return order

    def get_payment_url(self, order_id: str) -> str | None:
        """获取支付链接（真实模式用）"""
        order = self._orders.get(order_id)
        if not order or order.status != "pending":
            return None
        if self.mode == "mock":
            return f"/api/payment/pay/{order.id}/mock"
        # TODO: 真实支付 — 支付宝/微信 SDK
        return f"/api/payment/pay/{order.id}/pending"

    def cleanup_expired(self):
        """清理过期订单"""
        now = time.time()
        expired = [
            oid for oid, o in self._orders.items()
            if o.status == "pending" and now - o.created_at > ORDER_EXPIRE_SECONDS
        ]
        for oid in expired:
            self._orders[oid].status = "expired"
        if expired:
            logger.info(f"清理 {len(expired)} 个过期订单")


payment_service = PaymentService.get()
