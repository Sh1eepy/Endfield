# -*- coding: utf-8 -*-
"""
start_server.py — 统一服务启动入口（多 worker 支持）

用法:
    # 生产（默认 1 worker，避免重复加载模型和索引）
    python scripts/start_server.py
    # 或显式指定
    WEB_CONCURRENCY=2 python scripts/start_server.py

    # 本机开发调试（单进程，避免多进程各加载一次 embedding 模型占本机内存）
    WEB_CONCURRENCY=1 python scripts/start_server.py

worker 数来源（优先级）:
    1. 环境变量 WEB_CONCURRENCY（云端 Railway 注入 / 本机手动设）
    2. 默认 1（先观察服务器内存，再按需提高）
"""
import os
import sys

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")

# 把项目根加入 sys.path，使 uvicorn 能导入 scripts.api_server（无论从哪启动）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _load_env():
    """加载项目根 .env（LLM_API_KEY、FORWARDED_ALLOW_IPS 等），不覆盖已存在的环境变量。

    必须在读取启动配置前调用：uvicorn 会在加载 api_server（其内部才解析 .env）之前
    就消费 FORWARDED_ALLOW_IPS 环境变量，这里提前加载才能让 .env 里的配置真正生效。
    """
    env_path = os.path.join(ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


_load_env()

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT") or os.environ.get("WEB_PORT") or "8000")
WORKERS = int(os.environ.get("WEB_CONCURRENCY") or "1")
# 反向代理信任名单：None 时 uvicorn 回退默认 127.0.0.1；禁止填 *
FORWARDED_ALLOW_IPS = os.environ.get("FORWARDED_ALLOW_IPS")


def _prewarm():
    """启动期预加载 embedding 模型与 RAG/配方索引。

    把冷启动（模型加载 3~10s）从首个问答请求挪进健康检查的 start_period，
    首个用户不必承担加载卡顿。`RAG_PREWARM=0` 可关闭（如内存极紧的环境）。
    """
    if os.environ.get("RAG_PREWARM", "1") == "0":
        print("[start_server] 已关闭 RAG 预热（RAG_PREWARM=0）")
        return
    try:
        from rag_ask import warm_index
        print("[start_server] 预热 RAG 索引与 embedding 模型…")
        warm_index()
        print("[start_server] 预热完成")
    except Exception as exc:  # noqa: BLE001
        # 预热失败不阻断启动：首个问答仍会按惰性路径自行加载
        print(f"[start_server] 预热失败（将退回惰性加载）: {type(exc).__name__}: {exc}")


def main():
    import uvicorn

    # 单进程：直接跑（无 reload，生产模式）
    if WORKERS <= 1:
        _prewarm()
        print(f"[start_server] 单进程模式 http://{HOST}:{PORT}（本机开发推荐）")
        uvicorn.run("api_server:app", host=HOST, port=PORT, log_level="info",
                    forwarded_allow_ips=FORWARDED_ALLOW_IPS)
        return

    # 多 worker：每个 worker 独立进程，各自加载模型/索引（吃服务器内存）
    print(f"[start_server] 多 worker 模式: {WORKERS} 个进程 http://{HOST}:{PORT}")
    print(f"[start_server] 提示: 每个 worker 都会加载 embedding 模型与 RAG 索引，"
          f"worker 数越高并发越强但内存占用越大（确认内存余量后再提高）")
    uvicorn.run(
        "api_server:app",
        host=HOST,
        port=PORT,
        workers=WORKERS,
        log_level="info",
        forwarded_allow_ips=FORWARDED_ALLOW_IPS,
    )


if __name__ == "__main__":
    main()
