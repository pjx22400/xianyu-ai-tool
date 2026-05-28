# V2EX 帖子（复制粘贴到 v2ex.com 的 "分享创造" 节点）

**标题：** [分享创造] 给女朋友写了个闲鱼 AI 助手，结果搞成了完整 SaaS 平台

**正文：**

女朋友在闲鱼卖闲置，每天手动刷新、回复砍价太累了。

我就说给她写个机器人，结果越写越上头 😂

从爬虫脚本一路写成了多租户 SaaS：
- 📊 关键词监控：定时扫描，降价/上新自动推送
- 💬 AI 客服：DeepSeek 自动回复，支持人工接管
- 🔄 自动擦亮：定时刷新保持曝光
- 💰 利润追踪 + 数据导出 CSV
- 💳 支付系统（Mock 开箱即用）
- 🔧 管理后台（用户管理、收入统计）

技术栈：Python FastAPI + SQLite + DeepSeek + Docker

GitHub: https://github.com/pjx22400/xianyu-ai-tool

求 Star，求建议 🙏
