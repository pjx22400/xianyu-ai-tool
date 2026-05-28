# 🐟 闲鱼 AI 智能助手

基于闲鱼 H5 API 的智能商品管理与自动客服系统，支持多账号、AI 回复、订单检测和自动擦亮。

## 功能

### 📊 商品监控
- 关键词搜索 + 定时扫描新商品
- 降价 ≥1% 自动飞书通知
- Web 面板关键词 CRUD 管理

### 💬 智能客服
- WebSocket 长连接实时监听买家消息
- DeepSeek AI 多 Agent 路由回复（议价/技术/物流/成色/通用/招呼）
- 订单状态检测（已付款 → 自动提醒发货）

### 👤 多账号管理
- JSON 持久化存储，支持多账号独立 Cookie
- 默认账号设置，一键切换
- Web 面板可视化管理

### ⚡ 自动运营
- 定时自动擦亮商品，保持曝光排名
- 可在面板查看状态，手动触发擦亮

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，填入：
#   - DEEPSEEK_API_KEY（AI 回复）
#   - FEISHU_WEBHOOK（降价通知）
#   - XIANYU_COOKIES（闲鱼登录 Cookie）

# 3. 获取闲鱼 Cookie
python scripts/login.py  # Playwright 自动登录，输出 Cookie

# 4. 启动服务
python -m uvicorn src.main:app --host 0.0.0.0 --port 8000

# 5. 打开面板
open http://localhost:8000
```

## API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/health` | 健康检查（含各模块运行状态）|
| GET/POST/DELETE | `/api/keywords` | 关键词 CRUD |
| GET | `/api/items?keyword=` | 商品列表 |
| POST | `/api/scan?keyword=` | 手动触发扫描 |
| GET | `/api/status` | 监控状态 |
| POST | `/api/cs/start` | 启动智能客服 |
| POST | `/api/cs/stop` | 停止智能客服 |
| GET | `/api/cs/status` | 客服状态 |
| GET | `/api/cs/messages` | 最近消息 |
| GET/POST/PUT/DELETE | `/api/accounts` | 多账号 CRUD |
| POST | `/api/accounts/{id}/set-default` | 设为默认账号 |
| GET | `/api/refresh/status` | 自动擦亮状态 |
| POST | `/api/refresh/now` | 立即擦亮 |

## 技术栈

- **后端**: Python 3.11+, FastAPI, asyncio
- **数据库**: SQLite (aiosqlite)
- **AI**: DeepSeek API（多 Agent 路由回复）
- **采集**: 闲鱼 H5 REST API（签名算法）+ WebSocket（MessagePack）
- **通知**: 飞书 Webhook
- **前端**: 原生 HTML/CSS/JS（无框架依赖）

## 项目结构

```
xianyu-ai-tool/
├── src/
│   ├── config.py         # 全局配置
│   ├── models.py         # Pydantic 数据模型
│   ├── database.py       # SQLite + CRUD
│   ├── xianyu_api.py     # 闲鱼 H5 API 封装
│   ├── monitor.py        # 定时监控引擎
│   ├── notifier.py       # 飞书通知
│   ├── xianyu_ws.py      # 闲鱼 WebSocket 客户端
│   ├── reply_agent.py    # AI 回复引擎
│   ├── accounts.py       # 多账号管理
│   ├── auto_refresh.py   # 自动擦亮
│   └── main.py           # FastAPI 主入口（v0.3）
├── frontend/
│   └── dashboard.html    # 三 Tab 管理面板
├── scripts/
│   └── login.py          # Playwright 登录获取 Cookie
├── start.bat             # Windows 一键启动
└── requirements.txt
```

## 参考

- [ai-goofish-monitor](https://github.com/) — 闲鱼商品监控
- [XianyuAutoAgent](https://github.com/) — 闲鱼自动客服

## License

MIT
