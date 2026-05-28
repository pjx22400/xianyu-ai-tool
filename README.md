# 🐟 Xianyu AI Tool — 闲鱼 AI 智能助手

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-59%20passed-brightgreen)](tests/)
[![Version](https://img.shields.io/badge/version-0.6.2-orange)](https://github.com/pjx22400/xianyu-ai-tool)

**闲鱼卖家一站式 SaaS 平台** — 商品监控、智能客服、自动擦亮、多账号管理、利润追踪、支付系统。

> 🎯 为闲鱼卖家打造的 AI 运营工具，一条龙解决监控、客服、运营、变现。

---

## ✨ 功能

### 📊 商品监控
- 关键词定时扫描，自动检测新商品 & 降价
- 价格历史走势图（纯 SVG 柱状图，无外部依赖）
- 一键 CSV 导出（关键词 / 商品 / 利润 / 订单）

### 💬 智能客服
- WebSocket 监听闲鱼买家消息
- DeepSeek 驱动自动回复（议价 / 技术 / 通用三类 Bot）
- 人工接管：Dashboard 手动回复，5 秒冷却防刷屏
- 断线自动重连（指数退避 1→60s）

### 🔄 自动运营
- 商品自动擦亮，保持排名曝光
- 多账号管理（向导式 Cookie 获取 + 手动粘贴备用）

### 💰 利润追踪
- 记录每笔交易（进货价 / 卖出价 / 运费 / 平台费）
- 利润汇总 & 利润率计算

### 💳 支付系统
- **Mock 模式**（开发/测试）：一键完成支付
- **生产就绪**：预留支付宝/微信接口
- 价格方案：Pro 月度 ¥29 / 年度 ¥199
- 订单管理 + 订阅自动续期

### 🔧 管理后台
- 用户管理（升降级 / 到期管理）
- 收入统计面板
- 管理员双重权限判定

### 📧 邮件通知
- SMTP 配置（QQ / 163 / 126 / Gmail）
- 新商品 & 降价 HTML 邮件自动推送
- Dashboard 一键测试

### 📦 数据导出
- 关键词 / 商品 / 利润交易 / 支付订单 → CSV
- Excel / WPS / Google Sheets 直接打开

### 🏗️ 多租户 SaaS 架构
- JWT 认证 + bcrypt 密码加密
- 6 张业务表 `user_id` 隔离
- 免费 / Pro 双 tier 订阅
- 默认用户向后兼容

---

## 🚀 快速开始

```bash
# 1. 克隆
git clone https://github.com/pjx22400/xianyu-ai-tool.git
cd xianyu-ai-tool

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env：填入闲鱼 Cookie + DeepSeek API Key

# 3. 启动
docker compose up -d

# 4. 打开 Dashboard
# http://localhost:8000
```

---

## 📁 项目结构

```
├── src/
│   ├── main.py           # FastAPI 主入口（API 路由 800+ 行）
│   ├── database.py       # SQLite 数据层（10 张表 + CRUD）
│   ├── models.py         # Pydantic 数据模型
│   ├── auth.py           # JWT 认证 + 多租户
│   ├── monitor.py        # 商品监控扫描
│   ├── xianyu_api.py     # 闲鱼搜索 API 客户端
│   ├── xianyu_ws.py      # WebSocket 客服（断线重连）
│   ├── reply_agent.py    # DeepSeek 自动回复引擎
│   ├── auto_refresh.py   # 自动擦亮
│   ├── accounts.py       # 多账号管理
│   ├── notifier.py       # QQ Bot 通知（文件轮询）
│   ├── emailer.py        # SMTP 邮件通知
│   ├── export.py         # CSV 数据导出
│   ├── payment.py        # 支付系统（Mock + 预留真实）
│   └── config.py         # 配置（环境变量驱动）
├── frontend/
│   ├── dashboard.html    # 管理面板（7 个 Tab）
│   ├── login.html        # 登录页
│   └── landing.html      # Landing 页
├── tests/                # 59 个测试用例（pytest）
├── scripts/
│   └── login_auto.py     # 自动登录脚本
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── pyproject.toml
└── .github/workflows/ci.yml
```

---

## 🔧 技术栈

| 层级 | 技术 |
|------|------|
| **后端框架** | FastAPI (async) |
| **数据库** | SQLite (aiosqlite) |
| **认证** | JWT + bcrypt |
| **AI 引擎** | DeepSeek |
| **实时通信** | WebSocket (闲鱼 IM) |
| **部署** | Docker Compose |
| **通知** | QQ Bot + SMTP 邮件 |
| **测试** | pytest (59 cases) |
| **CI/CD** | GitHub Actions |

---

## 🧪 测试

```bash
# 运行核心测试（跳过性能测试）
pytest --ignore=tests/test_perf.py -v

# 运行全量
pytest -v
```

**59/59 通过** · 覆盖率：auth 93% · database 80% · models 100%

---

## 📊 Dashboard 面板

| Tab | 功能 |
|-----|------|
| 📊 商品监控 | 关键词管理 + 扫描 + 商品列表 |
| 💬 智能客服 | 实时消息 + 自动回复 + 手动接管 |
| 💰 利润追踪 | 交易记录 + 利润统计 |
| 👤 账号与运营 | 多账号 + 自动擦亮 + 📧 邮件设置 |
| ⭐ Pro 升级 | 方案对比 + 支付升级 |
| 📦 数据导出 | CSV 导出 + 📈 价格走势图 |
| 🔧 管理 | 用户管理 + 收入统计（管理员） |

---

## 🛣️ Roadmap

- [x] v0.5 — 多租户 SaaS 架构
- [x] v0.5.1 — 质量打磨（CI/CD + 审计）
- [x] v0.5.2 — 智能客服生产级升级
- [x] v0.6 — 支付系统 + 管理后台
- [x] v0.6.1 — 数据导出 + 价格历史
- [x] v0.6.2 — 邮件通知（QQ/163/Gmail）
- [ ] v0.7 — 真实支付接入（支付宝/微信）
- [ ] v0.8 — 移动端适配 / 小程序
- [ ] v1.0 — 生产部署（SSL + 域名 + 云服务器）

---

## 📝 License

MIT © [pjx22400](https://github.com/pjx22400)
