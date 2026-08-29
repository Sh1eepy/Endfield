"""API access controls; SQLite counters are shared by workers on one host.

Limits count admitted requests, not LLM calls/tokens. Failed requests are not
refunded: a failed response may already have consumed provider credits.
"""
import hashlib
import hmac
import ipaddress
import logging
import math
import os
import sqlite3
import time
from contextlib import closing
from pathlib import Path

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


def positive_int_env(name, default):
    try:
        value = int(os.environ.get(name) or default)
        return value if value > 0 else default
    except (TypeError, ValueError):
        return default


class AskBudget:
    def __init__(self, path, per_minute=6, per_ip_day=60, per_day=200, namespace=""):
        self.path = Path(path)
        self.per_minute = per_minute
        self.per_ip_day = per_ip_day
        self.per_day = per_day
        self.namespace = namespace.strip()

    def consume(self, client, now=None):
        now = time.time() if now is None else now
        minute, day = int(now // 60), int(now // 86400)
        client_key = hashlib.sha256(client.encode("utf-8")).hexdigest()
        prefix = f"{self.namespace}-" if self.namespace else ""
        limits = (
            (prefix + "ip-minute", client_key, minute, (minute + 1) * 60,
             self.per_minute, "请求过于频繁，请稍后重试"),
            (prefix + "ip-day", client_key, day, (day + 1) * 86400,
             self.per_ip_day, "此 IP 今日问答次数已用完"),
            (prefix + "global-day", "all", day, (day + 1) * 86400,
             self.per_day, "本站今日问答次数已用完"),
        )
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with closing(sqlite3.connect(self.path, timeout=2)) as conn:
                conn.execute("""CREATE TABLE IF NOT EXISTS ask_usage (
                    scope TEXT, client TEXT, bucket INTEGER,
                    expires INTEGER NOT NULL, used INTEGER NOT NULL,
                    PRIMARY KEY (scope, client, bucket))""")
                # One atomic admission across all three limits and all workers.
                with conn:
                    conn.execute("BEGIN IMMEDIATE")
                    conn.execute("DELETE FROM ask_usage WHERE expires <= ?", (now,))
                    for scope, key, bucket, expires, limit, detail in limits:
                        row = conn.execute(
                            "SELECT used FROM ask_usage WHERE scope=? AND client=? AND bucket=?",
                            (scope, key, bucket),
                        ).fetchone()
                        if row and row[0] >= limit:
                            raise HTTPException(429, detail, headers={
                                "Retry-After": str(max(1, math.ceil(expires - now)))})
                    for scope, key, bucket, expires, _, _ in limits:
                        conn.execute("""INSERT INTO ask_usage VALUES (?, ?, ?, ?, 1)
                            ON CONFLICT(scope, client, bucket)
                            DO UPDATE SET used=used+1""", (scope, key, bucket, expires))
        except (OSError, sqlite3.Error) as exc:
            logger.error("Ask budget store unavailable: %s", type(exc).__name__)
            # Never silently allow paid calls when quota storage fails.
            raise HTTPException(503, "问答额度保护暂不可用，请稍后重试",
                                headers={"Retry-After": "5"}) from exc


ROOT = Path(__file__).resolve().parent.parent
API_ACCESS_TOKEN = os.environ.get("API_ACCESS_TOKEN", "").strip()
ASK_BUDGET = AskBudget(
    os.environ.get("ASK_BUDGET_DB") or ROOT / "logs" / "api-security" / "ask-budget.sqlite3",
    positive_int_env("ASK_RATE_PER_MINUTE", 6),
    positive_int_env("ASK_IP_DAILY_LIMIT", 60),
    positive_int_env("ASK_DAILY_LIMIT", 200),
)
FEEDBACK_BUDGET = AskBudget(
    os.environ.get("ASK_BUDGET_DB") or ROOT / "logs" / "api-security" / "ask-budget.sqlite3",
    positive_int_env("FEEDBACK_RATE_PER_MINUTE", 20),
    positive_int_env("FEEDBACK_IP_DAILY_LIMIT", 200),
    positive_int_env("FEEDBACK_DAILY_LIMIT", 1000),
    namespace="feedback",
)


def _valid_token(request):
    scheme, _, token = request.headers.get("authorization", "").partition(" ")
    return bool(API_ACCESS_TOKEN) and scheme.lower() == "bearer" and hmac.compare_digest(
        token.encode("utf-8"), API_ACCESS_TOKEN.encode("utf-8"))


def require_ask_access(request: Request):
    if API_ACCESS_TOKEN and not _valid_token(request):
        raise HTTPException(401, "需要有效的访问令牌",
                            headers={"WWW-Authenticate": "Bearer"})
    # Only use ASGI client identity; do not parse arbitrary forwarding headers.
    client = request.client.host if request.client else "unknown"
    ASK_BUDGET.consume(client)


def require_feedback_access(request: Request):
    if API_ACCESS_TOKEN and not _valid_token(request):
        raise HTTPException(401, "需要有效的访问令牌",
                            headers={"WWW-Authenticate": "Bearer"})
    client = request.client.host if request.client else "unknown"
    FEEDBACK_BUDGET.consume(client)


def require_admin_access(request: Request):
    if _valid_token(request):
        return
    try:
        if request.client and ipaddress.ip_address(request.client.host).is_loopback:
            return
    except ValueError:
        pass
    raise HTTPException(403, "管理接口仅限本机或有效访问令牌")
