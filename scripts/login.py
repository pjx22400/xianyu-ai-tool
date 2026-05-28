"""闲鱼登录助手 — Playwright 浏览器自动提取 Cookie

运行方式:
    python scripts/login.py

流程:
    1. 打开闲鱼登录页
    2. 等待用户手动扫码/登录（60 秒超时）
    3. 自动提取 Cookie 写入 .env
"""
import asyncio
import sys
import os
from pathlib import Path

# 添加项目根目录到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("请先安装 playwright: pip install playwright && playwright install chromium")
    sys.exit(1)


ENV_FILE = Path(__file__).parent.parent / ".env"
LOGIN_URL = "https://www.goofish.com/"


def save_cookies(cookies_str: str):
    """将 Cookie 写入 .env 文件"""
    content = ENV_FILE.read_text(encoding="utf-8")
    # 替换 XIANYU_COOKIES 行
    new_lines = []
    for line in content.splitlines():
        if line.startswith("XIANYU_COOKIES="):
            new_lines.append(f"XIANYU_COOKIES={cookies_str}")
        else:
            new_lines.append(line)
    ENV_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"\n✅ Cookie 已保存到 {ENV_FILE}")


async def main():
    print("=" * 50)
    print("  闲鱼登录助手")
    print("=" * 50)
    print()
    print("即将打开浏览器，请在浏览器中扫码或账号密码登录闲鱼。")
    print("登录成功后，程序会自动提取 Cookie 并关闭浏览器。")
    print()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="zh-CN",
        )
        page = await context.new_page()

        # 打开闲鱼首页
        await page.goto(LOGIN_URL)
        print("⏳ 浏览器已打开，请登录闲鱼...")

        # 等待用户登录（检测 URL 变化或最多等 120 秒）
        try:
            await page.wait_for_url(
                "**/www.goofish.com/**",
                timeout=120_000,
            )
            # 额外等几秒确保 Cookie 完全设置
            await asyncio.sleep(3)

            # 检查是否真的登录了
            current_url = page.url
            if "passport" in current_url or "login" in current_url:
                print("⚠️  似乎未完成登录，请确认已登录后按回车继续...")
                input()
                await asyncio.sleep(2)

        except Exception:
            print("\n⏰ 超时。如果你已经登录了，按回车继续提取 Cookie...")
            input()

        # 获取所有 Cookie
        cookies = await context.cookies()
        if not cookies:
            print("❌ 未获取到任何 Cookie，请重试")
            await browser.close()
            return

        # 转为字符串
        cookie_parts = []
        for c in cookies:
            cookie_parts.append(f"{c['name']}={c['value']}")

        cookies_str = "; ".join(cookie_parts)
        print(f"\n📋 获取到 {len(cookies)} 个 Cookie")

        # 检查关键 Cookie
        key_cookies = ["_m_h5_tk", "unb", "cookie2", "XSRF-TOKEN"]
        found = [k for k in key_cookies if any(c['name'] == k for c in cookies)]
        missing = [k for k in key_cookies if k not in found]
        if found:
            print(f"   ✅ 关键 Cookie: {', '.join(found)}")
        if missing:
            print(f"   ⚠️  缺少: {', '.join(missing)}（可能影响功能）")

        # 保存到 .env
        save_cookies(cookies_str)

        await browser.close()
        print("\n🎉 完成！现在可以启动服务了：")
        print("   cd E:\\xianyu-ai-tool")
        print("   python -m src.main")


if __name__ == "__main__":
    asyncio.run(main())
