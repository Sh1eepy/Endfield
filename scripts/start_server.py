# -*- coding: utf-8 -*-
"""
start_server.py — 统一服务启动入口（多 worker 支持）

用法:
    # 生产（云端，默认 4 worker，吃云服务器内存）
    python scripts/start_server.py
    # 或显式指定
    WEB_CONCURRENCY=4 python scripts/start_server.py

    # 本机开发调试（单进程，避免多进程各加载一次 embedding 模型占本机内存）
    WEB_CONCURRENCY=1 python scripts/start_server.py

worker 数来源（优先级）:
    1. 环境变量 WEB_CONCURRENCY（云端 Railway 注入 / 本机手动设）
    2. 默认 4（面向云端生产；本机开发请显式设 1）
"""
import os
import sys

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")

# 把项目根加入 sys.path，使 uvicorn 能导入 scripts.api_server（无论从哪启动）
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

HOST = os.environ.get("HOST", "0.0.0.0")
PORT = int(os.environ.get("PORT") or os.environ.get("WEB_PORT") or "8000")
WORKERS = int(os.environ.get("WEB_CONCURRENCY") or "4")


def main():
    import uvicorn

    # 单进程：直接跑（无 reload，生产模式）
    if WORKERS <= 1:
        print(f"[start_server] 单进程模式 http://{HOST}:{PORT}（本机开发推荐）")
        uvicorn.run("api_server:app", host=HOST, port=PORT, log_level="info")
        return

    # 多 worker：每个 worker 独立进程，各自加载模型/索引（吃服务器内存）
    print(f"[start_server] 多 worker 模式: {WORKERS} 个进程 http://{HOST}:{PORT}")
    print(f"[start_server] 提示: 每个 worker 都会加载 embedding 模型与 RAG 索引，"
          f"worker 数越高并发越强但内存占用越大（云端生产建议 2-4）")
    uvicorn.run(
        "api_server:app",
        host=HOST,
        port=PORT,
        workers=WORKERS,
        log_level="info",
    )


if __name__ == "__main__":
    main()
