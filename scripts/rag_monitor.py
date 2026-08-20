# -*- coding: utf-8 -*-
"""单进程 RAG 请求指标；不记录查询正文或密钥。"""
from collections import Counter, deque
from threading import Lock
import time


class RAGMonitor:
    """记录单进程请求、路由、降级和延迟；数据不跨重启持久化。"""
    def __init__(self, latency_window=500):
        self.started_at = time.time()
        self.counts = Counter({key: 0 for key in (
            "requests", "errors", "empty_retrieval", "rejected",
            "llm_degraded", "answers_generated",
        )})
        self.routes = Counter()
        self.errors = Counter()
        self.latencies = deque(maxlen=latency_window)
        self.lock = Lock()

    def observe(self, result, elapsed_ms, gen_requested=True, error=None):
        with self.lock:
            self.counts["requests"] += 1
            self.latencies.append(float(elapsed_ms))
            if error:
                self.counts["errors"] += 1
                self.errors[type(error).__name__] += 1
                return
            route = str((result or {}).get("route_used") or "unknown")
            self.routes[route] += 1
            hits = (result or {}).get("hits")
            if route == "rag" and not hits:
                self.counts["empty_retrieval"] += 1
            if (result or {}).get("rejected"):
                self.counts["rejected"] += 1
            needs_llm = gen_requested and route in {"rag", "enum"}
            if needs_llm and not (result or {}).get("answer") and not (result or {}).get("rejected"):
                self.counts["llm_degraded"] += 1
            if (result or {}).get("answer"):
                self.counts["answers_generated"] += 1

    def snapshot(self):
        with self.lock:
            values = sorted(self.latencies)
            def pct(p):
                if not values:
                    return 0.0
                return round(values[min(len(values) - 1, int((len(values) - 1) * p))], 2)
            total = self.counts["requests"] or 1
            return {
                "uptime_seconds": round(time.time() - self.started_at, 1),
                "counts": dict(self.counts), "routes": dict(self.routes), "errors": dict(self.errors),
                "rates": {
                    "error": round(self.counts["errors"] / total, 4),
                    "empty_retrieval": round(self.counts["empty_retrieval"] / total, 4),
                    "llm_degraded": round(self.counts["llm_degraded"] / total, 4),
                    "rejected": round(self.counts["rejected"] / total, 4),
                },
                "latency_ms": {"p50": pct(.50), "p95": pct(.95), "max": round(max(values), 2) if values else 0.0},
            }


monitor = RAGMonitor()
