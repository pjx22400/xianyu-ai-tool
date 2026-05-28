# 🐟 闲鱼 AI 助手 — 我写了一个能赚钱的开源 SaaS 项目

> 一个周末搭的闲鱼卖家工具，没想到搞成了完整 SaaS 平台。监控 + 客服 + 支付 + 多租户，全栈可部署。

---

## 为什么做这个

女朋友在闲鱼卖闲置，每天手动刷新商品、回复砍价消息，烦得要死。

我说：**我给你写个机器人吧。**

结果越写越上头，从爬虫脚本一路写成了多租户 SaaS 平台——商品监控、AI 自动回复、利润追踪、支付系统、管理后台，全都有了。

---

## 能干什么

| 功能 | 说明 |
|------|------|
| 📊 商品监控 | 关键词定时扫描，降价/上新自动通知 |
| 💬 AI 客服 | DeepSeek 自动回复砍价/咨询，支持人工接管 |
| 🔄 自动擦亮 | 定时刷新商品，保持曝光排名 |
| 💰 利润追踪 | 记录每笔交易，算利润率和收益 |
| 💳 支付系统 | Mock 模式开箱即用，预留支付宝/微信 |
| 📧 邮件通知 | QQ/163/Gmail 推送新商品和降价 |
| 📦 数据导出 | 一键 CSV 导出，Excel 直接分析 |
| 🔧 管理后台 | 用户管理、收入统计、订阅升降级 |

Dashboard 7 个 Tab，一条龙搞定。

---

## 技术栈

```
后端: Python 3.11 + FastAPI + SQLite (aiosqlite)
AI:   DeepSeek（意图分类 + 自动回复）
通信: WebSocket（闲鱼 IM 实时监听）
认证: JWT + bcrypt 多租户隔离
支付: Mock 模式 + 预留支付宝/微信
部署: Docker Compose 一键启动
测试: 59 个测试用例，GitHub Actions CI
```

---

## 架构亮点

- **多租户 SaaS**：6 张业务表 user_id 隔离，免费/Pro 双 tier
- **生产级客服**：WebSocket 断线重连（指数退避），5 秒防刷屏
- **自动化运营**：定时扫描 + 自动擦亮，挂机就能跑
- **完整支付链路**：Mock 支付 → 订单 → 订阅激活，接入真实支付只需改 2 行

---

## 快速体验

```bash
git clone https://github.com/pjx22400/xianyu-ai-tool
cd xianyu-ai-tool
cp .env.example .env  # 填 DeepSeek API Key + 闲鱼 Cookie
docker compose up -d
# 打开 http://localhost:8000
```

Dashboard 即可管理一切。

---

## 适合谁

- 闲鱼卖家 / 二手商贩，想自动化运营
- 独立开发者，想参考 SaaS 架构设计
- 想学习 FastAPI + AI Agent 实战的同学

---

## 后续计划

- [ ] 真实支付接入（支付宝/微信）
- [ ] 移动端适配
- [ ] 小程序版本

---

⭐ 觉得有用的话，GitHub 点个 Star 支持一下！

🔗 https://github.com/pjx22400/xianyu-ai-tool

#开源 #Python #闲鱼 #SaaS #AI
