# Xianyu AI Tool — 闲鱼 AI 智能助手

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

闲鱼卖家一站式 AI 工具：商品监控 + 智能客服 + 自动擦亮 + 多账号管理。

## ✨ 功能

- **📊 商品监控** — 关键词定时扫描，降价/上新自动推送通知
- **💬 智能客服** — WebSocket 监听买家消息，DeepSeek 驱动自动回复（议价/技术/通用三类 Bot）
- **🔄 自动擦亮** — 定时擦亮商品，保持曝光
- **👤 多账号** — 支持多个闲鱼号，一键登录获取 Cookie
- **🔔 QQ 通知** — 降价/上新/订单状态变更实时推送到 QQ
- **📱 Dashboard** — 三 Tab Web 面板（监控/客服/账号）

## 🚀 快速开始

```bash
# 1. 配置
cp .env.example .env
# 编辑 .env：填入闲鱼 Cookie + DeepSeek API Key

# 2. 启动
docker compose up -d

# 3. 打开 Dashboard
open http://localhost:8000
```

## 📁 项目结构

```
├── src/
│   ├── main.py          # FastAPI 主入口
│   ├── monitor.py       # 商品监控
│   ├── xianyu_api.py    # 闲鱼搜索 API
│   ├── xianyu_ws.py     # WebSocket 客服
│   ├── reply_agent.py   # DeepSeek 回复引擎
│   ├── auto_refresh.py  # 自动擦亮
│   ├── accounts.py      # 多账号管理
│   ├── notifier.py      # 通知模块
│   └── database.py      # SQLite 数据层
├── frontend/
│   └── dashboard.html   # 管理面板
├── scripts/
│   └── login_auto.py    # 自动登录脚本
├── docker-compose.yml
├── Dockerfile
└── requirements.txt
```

## 🔧 技术栈

- **后端**: FastAPI + SQLite (async)
- **AI**: DeepSeek (意图分类 + 自动回复)
- **通信**: WebSocket (闲鱼 IM)
- **部署**: Docker Compose
- **通知**: QQ Bot (文件轮询)

## 📝 License

MIT
