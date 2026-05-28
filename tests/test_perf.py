"""性能基准测试 — 测量关键路径延迟"""
import time, statistics, json
import urllib.request

BASE = "http://localhost:8000"
WARMUP = 3
RUNS = 20

def req(path, body=None, token=None, method="GET"):
    """Helper: make HTTP request, return response"""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = json.dumps(body).encode() if body else None
    rq = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    return urllib.request.urlopen(rq)

def bench(name, fn, warmup=WARMUP, runs=RUNS):
    for _ in range(warmup):
        fn()
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        times.append((time.perf_counter() - start) * 1000)
    avg = statistics.mean(times)
    p50 = statistics.median(times)
    p95 = sorted(times)[int(len(times) * 0.95)]
    print(f"  {name:30s}  avg={avg:6.1f}ms  p50={p50:6.1f}ms  p95={p95:6.1f}ms")
    return {"name": name, "avg": avg, "p50": p50, "p95": p95}

# 注册获取 token
ts = int(time.time())
email = f"perf_{ts}@test.com"
resp = req("/api/auth/register", {"email": email, "password": "perf123456"}, method="POST")
token = json.loads(resp.read())["access_token"]

print("=" * 70)
print("闲鱼 AI v0.5 — 性能基准测试")
print(f"  {RUNS} 次运行 (Warmup: {WARMUP})")
print("=" * 70)

results = [
    bench("GET /api/health",          lambda: req("/api/health")),
    bench("GET /api/auth/me",         lambda: req("/api/auth/me", token=token)),
    bench("POST /api/keywords",       lambda: req("/api/keywords", {"keyword": "p"}, token=token, method="POST")),
    bench("GET /api/keywords",        lambda: req("/api/keywords", token=token)),
    bench("GET / (Landing)",          lambda: req("/")),
    bench("POST /api/deals",          lambda: req("/api/deals", {"item_title":"p","sell_price":100}, token=token, method="POST")),
    bench("GET /api/deals/summary",   lambda: req("/api/deals/summary", token=token)),
]

print("\n" + "=" * 70)
all_avg = statistics.mean([r["avg"] for r in results])
worst = max(results, key=lambda r: r["avg"])
print(f"Overall avg: {all_avg:.1f}ms  |  Slowest: {worst['name']} ({worst['avg']:.1f}ms)")
if all_avg < 50:       print("🏆 Excellent (sub-50ms)")
elif all_avg < 100:    print("✅ Good (sub-100ms)")
elif all_avg < 200:    print("⚠️ Acceptable (sub-200ms)")
else:                  print("🔴 Needs optimization")
print("=" * 70)
