"""邮件通知模块 v0.6 — SMTP 发送邮件

支持国内邮箱：QQ、163、126、Gmail、自定义 SMTP
"""

import asyncio
import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
from dataclasses import dataclass

logger = logging.getLogger("emailer")

# 预置国内邮箱 SMTP 配置
PRESETS = {
    "qq": {"host": "smtp.qq.com", "port": 587, "tls": True},
    "163": {"host": "smtp.163.com", "port": 465, "tls": False, "ssl": True},
    "126": {"host": "smtp.126.com", "port": 465, "tls": False, "ssl": True},
    "gmail": {"host": "smtp.gmail.com", "port": 587, "tls": True},
}


@dataclass
class EmailConfig:
    smtp_host: str
    smtp_port: int
    sender_email: str
    sender_password: str  # 授权码
    use_tls: bool = True
    use_ssl: bool = False
    notify_new_items: bool = True
    notify_price_drops: bool = True


def _get_smtp(config: EmailConfig) -> smtplib.SMTP:
    """创建 SMTP 连接"""
    if config.use_ssl:
        server = smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, timeout=15)
    else:
        server = smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=15)
        if config.use_tls:
            server.starttls()
    server.login(config.sender_email, config.sender_password)
    return server


async def send_email(config: EmailConfig, to_email: str, subject: str, html_body: str) -> bool:
    """发送 HTML 邮件"""
    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = config.sender_email
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html", "utf-8"))

        loop = asyncio.get_event_loop()
        server = await loop.run_in_executor(None, _get_smtp, config)
        await loop.run_in_executor(None, server.sendmail,
                                   config.sender_email, to_email, msg.as_string())
        server.quit()
        logger.info(f"邮件已发送: {subject} → {to_email}")
        return True

    except Exception as e:
        logger.error(f"邮件发送失败 ({config.sender_email} → {to_email}): {e}")
        return False


def _build_new_items_email(keyword: str, items: list[dict]) -> str:
    """生成新商品通知邮件（HTML）"""
    rows = []
    for it in items[:20]:
        price = it.get("price", 0)
        title = it.get("title", "无标题")[:50]
        seller = it.get("seller", "?")
        item_id = it.get("item_id", "")
        url = f"https://www.goofish.com/item?id={item_id}"
        rows.append(f"""
        <tr>
            <td style="padding:8px 12px;border-bottom:1px solid #eee">
                <a href="{url}" style="color:#ff5000;text-decoration:none">{title}</a>
            </td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#ff5000;font-weight:bold">
                ¥{price}
            </td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#666">{seller}</td>
        </tr>""")

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:600px;margin:0 auto">
    <div style="background:linear-gradient(135deg,#ff5000,#ff7a45);padding:20px;color:#fff;border-radius:8px 8px 0 0">
        <h2 style="margin:0">🆕 闲鱼新商品提醒</h2>
        <p style="margin:4px 0 0;opacity:.8">关键词: {keyword} | 共 {len(items)} 件</p>
    </div>
    <div style="background:#fff;padding:16px;border:1px solid #eee;border-radius:0 0 8px 8px">
        <table style="width:100%;border-collapse:collapse">
            <tr style="background:#fafafa"><th style="padding:8px 12px;text-align:left;font-size:12px;color:#999">商品</th>
            <th style="padding:8px 12px;text-align:left;font-size:12px;color:#999">价格</th>
            <th style="padding:8px 12px;text-align:left;font-size:12px;color:#999">卖家</th></tr>
            {''.join(rows)}
        </table>
        {'<p style="color:#999;font-size:12px;margin-top:8px">... 还有 ' + str(len(items) - 20) + ' 件</p>' if len(items) > 20 else ''}
    </div>
    <p style="color:#999;font-size:11px;text-align:center;margin-top:12px">
        闲鱼 AI 智能助手 · <a href="http://localhost:8000" style="color:#ff5000">打开 Dashboard</a>
    </p>
</body></html>"""


def _build_price_drops_email(keyword: str, items: list[dict]) -> str:
    """生成降价通知邮件（HTML）"""
    rows = []
    for it in items[:20]:
        price = it.get("price", 0)
        old_price = it.get("old_price", 0)
        drop = it.get("price_drop_amount", 0)
        title = it.get("title", "无标题")[:50]
        item_id = it.get("item_id", "")
        url = f"https://www.goofish.com/item?id={item_id}"
        rows.append(f"""
        <tr>
            <td style="padding:8px 12px;border-bottom:1px solid #eee">
                <a href="{url}" style="color:#ff5000;text-decoration:none">{title}</a>
            </td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee">
                <span style="text-decoration:line-through;color:#999">¥{old_price}</span>
                → <span style="color:#52c41a;font-weight:bold">¥{price}</span>
            </td>
            <td style="padding:8px 12px;border-bottom:1px solid #eee;color:#52c41a;font-weight:bold">
                -¥{drop}
            </td>
        </tr>""")

    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"></head>
<body style="font-family:-apple-system,BlinkMacSystemFont,sans-serif;max-width:600px;margin:0 auto">
    <div style="background:linear-gradient(135deg,#52c41a,#73d13d);padding:20px;color:#fff;border-radius:8px 8px 0 0">
        <h2 style="margin:0">📉 闲鱼降价提醒</h2>
        <p style="margin:4px 0 0;opacity:.8">关键词: {keyword} | 共 {len(items)} 件降价</p>
    </div>
    <div style="background:#fff;padding:16px;border:1px solid #eee;border-radius:0 0 8px 8px">
        <table style="width:100%;border-collapse:collapse">
            <tr style="background:#fafafa"><th style="padding:8px 12px;text-align:left;font-size:12px;color:#999">商品</th>
            <th style="padding:8px 12px;text-align:left;font-size:12px;color:#999">价格变化</th>
            <th style="padding:8px 12px;text-align:left;font-size:12px;color:#999">降幅</th></tr>
            {''.join(rows)}
        </table>
        {'<p style="color:#999;font-size:12px;margin-top:8px">... 还有 ' + str(len(items) - 20) + ' 件降价</p>' if len(items) > 20 else ''}
    </div>
    <p style="color:#999;font-size:11px;text-align:center;margin-top:12px">
        闲鱼 AI 智能助手 · <a href="http://localhost:8000" style="color:#52c41a">打开 Dashboard</a>
    </p>
</body></html>"""


async def notify_new_items_email(config: EmailConfig, to_email: str, keyword: str, items: list[dict]) -> bool:
    if not config.notify_new_items:
        return False
    html = _build_new_items_email(keyword, items)
    return await send_email(config, to_email, f"🆕 闲鱼新商品 — {keyword} ({len(items)}件)", html)


async def notify_price_drops_email(config: EmailConfig, to_email: str, keyword: str, items: list[dict]) -> bool:
    if not config.notify_price_drops:
        return False
    html = _build_price_drops_email(keyword, items)
    return await send_email(config, to_email, f"📉 闲鱼降价 — {keyword} ({len(items)}件)", html)
