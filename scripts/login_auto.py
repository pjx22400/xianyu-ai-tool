"""闲鱼自动登录 - 浏览器 Cookie 提取

用法：
    python login_auto.py [账号ID] [备注名] [API地址]

流程：
    1. 打开系统默认浏览器 → 闲鱼登录页
    2. 你在浏览器里扫码或输密码登录
    3. 登录后复制 JS 代码到浏览器控制台
    4. Cookie 通过 API 自动写入 Docker 服务
"""

import json
import sys
import time
import webbrowser
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlencode
from urllib.request import urlopen, Request
import threading

PROJECT_DIR = Path(__file__).parent.parent
ACCOUNTS_FILE = PROJECT_DIR / "data" / "accounts.json"
RECEIVED_COOKIES = None
SERVER_READY = threading.Event()


class CookieReceiver(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_POST(self):
        global RECEIVED_COOKIES
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8")
        RECEIVED_COOKIES = body

        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write("""
            <html><body style="font-family:sans-serif;text-align:center;padding:50px">
            <h1>Cookie OK!</h1><p>Close this window</p>
            </body></html>
        """.encode("utf-8"))

    def log_message(self, format, *args):
        pass


def start_server(port: int = 19876):
    server = HTTPServer(("127.0.0.1", port), CookieReceiver)
    SERVER_READY.set()
    server.handle_request()


def save_via_api(api_url: str, account_id: str, name: str, cookies_str: str) -> bool:
    """通过 API 保存账号，同时更新本地 accounts.json"""
    try:
        payload = json.dumps({
            "id": account_id,
            "name": name or account_id,
            "cookies": cookies_str,
            "enabled": True,
            "is_default": False,
        }).encode("utf-8")

        # 1. 通过 API 写入 Docker 服务
        req = Request(
            f"{api_url}/api/accounts",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urlopen(req, timeout=5)
        result = json.loads(resp.read())
        if result.get("ok"):
            print(f"\n[OK] '{account_id}' API sync success")
        else:
            print(f"\n[WARN] API response: {result}")
    except Exception as e:
        print(f"\n[WARN] API sync failed: {e}")
        print(f"      Saving to local accounts.json instead")

    # 2. 同时写入本地 accounts.json（fallback）
    try:
        ACCOUNTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        existing = json.loads(ACCOUNTS_FILE.read_text("utf-8")) if ACCOUNTS_FILE.exists() else []
        old = next((a for a in existing if a.get("id") == account_id), None)
        if old:
            old.update({"cookies": cookies_str, "name": name or old.get("name", ""), "enabled": True})
        else:
            existing.append({
                "id": account_id, "name": name or account_id,
                "cookies": cookies_str, "enabled": True,
                "is_default": len(existing) == 0,
            })
        ACCOUNTS_FILE.write_text(json.dumps(existing, ensure_ascii=False, indent=2), "utf-8")
        print(f"[OK] Saved locally: {len(existing)} accounts")
    except Exception as e:
        print(f"[ERR] Local save failed: {e}")
        return False

    return True


def main():
    global RECEIVED_COOKIES
    account_id = sys.argv[1] if len(sys.argv) > 1 else "main"
    name = sys.argv[2] if len(sys.argv) > 2 else ""
    api_url = sys.argv[3] if len(sys.argv) > 3 else "http://127.0.0.1:8000"

    PORT = 19876
    JS_CODE = f"""// Paste ALL of this into browser Console (F12), then Enter
(function() {{
    fetch('http://127.0.0.1:{PORT}', {{
        method: 'POST',
        headers: {{'Content-Type': 'text/plain'}},
        body: document.cookie
    }}).catch(e => console.error(e));
}})();
"""

    print("=" * 60)
    print(f"  Xianyu Login - Account: {account_id}")
    print("=" * 60)
    print()
    print("Steps:")
    print("  1. Browser opens goofish.com")
    print("  2. Scan QR or enter password to login")
    print("  3. After login, press F12, go to Console tab")
    print("  4. Copy + paste the code below, press Enter")
    print()
    print("  " + "=" * 52)
    print("  Paste this in browser Console:")
    print("  " + JS_CODE.replace("\n", "\n  "))
    print("  " + "=" * 52)
    print()

    server_thread = threading.Thread(target=start_server, args=(PORT,), daemon=True)
    server_thread.start()
    SERVER_READY.wait()

    webbrowser.open("https://www.goofish.com/")
    print("Browser opened")
    print("Waiting for login + JS extraction...")
    print()

    for i in range(180):
        if RECEIVED_COOKIES:
            break
        time.sleep(1)

    if not RECEIVED_COOKIES:
        print("Timeout: no cookies received in 3 min")
        return

    print(f"\nCookies received ({len(RECEIVED_COOKIES)} chars)")

    for key in ["_m_h5_tk", "unb", "cookie2"]:
        found = key in RECEIVED_COOKIES
        print(f"  {'OK' if found else 'MISSING'} {key}")

    save_via_api(api_url, account_id, name, RECEIVED_COOKIES)
    print(f"\nDone! Dashboard -> Accounts ({api_url})")


if __name__ == "__main__":
    main()
