"""数据模型 — Pydantic 模型定义"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class MonitorKeyword(BaseModel):
    """监控关键词"""
    id: Optional[int] = None
    keyword: str = Field(..., description="搜索关键词")
    min_price: Optional[float] = Field(None, description="最低价格过滤")
    max_price: Optional[float] = Field(None, description="最高价格过滤")
    enabled: bool = Field(True, description="是否启用")
    created_at: Optional[datetime] = None


class XianyuItem(BaseModel):
    """闲鱼商品"""
    item_id: str = Field(..., description="商品 ID")
    title: str = Field(..., description="标题")
    price: float = Field(..., description="当前价格（元）")
    old_price: Optional[float] = Field(None, description="原始价格")
    seller: str = Field("", description="卖家昵称")
    location: str = Field("", description="所在地")
    image_url: str = Field("", description="主图 URL")
    item_url: str = Field("", description="商品链接")
    keyword: str = Field("", description="匹配的关键词")
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    is_new: bool = Field(False, description="是否新上架")
    price_dropped: bool = Field(False, description="是否降价")
    price_drop_amount: float = Field(0.0, description="降价金额")


class MonitorResult(BaseModel):
    """一次监控扫描的结果"""
    keyword: str
    total_items: int
    new_items: int
    price_drops: int
    items: list[XianyuItem]
    scanned_at: datetime


class KeywordCreate(BaseModel):
    """创建关键词请求"""
    keyword: str
    min_price: Optional[float] = None
    max_price: Optional[float] = None


class DealCreate(BaseModel):
    """记录一笔交易"""
    item_title: str = Field(..., description="商品名称")
    cost_price: float = Field(0, description="进货价（元）")
    sell_price: float = Field(..., description="卖出价（元）")
    shipping_cost: float = Field(0, description="运费（元）")
    platform_fee: float = Field(0, description="平台手续费")
    notes: str = Field("", description="备注")
