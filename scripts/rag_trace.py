"""持久化 RAG Trace、用户反馈与坏例隔离区。

普通 Trace 只保存查询指纹和长度；只有用户主动反馈时才在 feedback 表保存查询正文。
"""
import hashlib
import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from scripts.rag_prompts import PROMPT_VERSIONS


ROOT = Path(__file__).resolve().parent.parent
TRACE_SCHEMA_VERSION = "2"
TRACE_DB = Path(os.environ.get("RAG_TRACE_DB") or ROOT / "logs" / "observability" / "rag-trace.sqlite3")


def query_fingerprint(query):
    normalized = " ".join(str(query or "").strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def content_fingerprint(content):
    """回答快照按原始字节校验，不沿用会折叠空白的 query 规范化。"""
    return hashlib.sha256(str(content or "").encode("utf-8")).hexdigest()


def _json(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def feedback_snapshot(result):
    """生成前后端共同提交的稳定回答快照；Trace 只保存其 hash。"""
    if not isinstance(result, dict):
        return ""
    if result.get("feedback_snapshot"):
        return str(result["feedback_snapshot"])
    if result.get("answer"):
        return str(result["answer"])
    summary = {key: result.get(key) for key in (
        "route", "route_used", "item", "device", "recipes", "matches", "names", "error")
        if result.get(key) is not None}
    return json.dumps(summary, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hit_ref(hit, rank):
    meta = hit.get("meta") or {}
    return {
        "rank": rank,
        "item_id": str(meta.get("item_id") or ""),
        "chunk_index": meta.get("chunk_index"),
        "name": str(meta.get("name") or "")[:100],
        "category": str(meta.get("category") or "")[:50],
        "score": hit.get("score"),
        "vector_sim": hit.get("vector_sim"),
        "bm25_score": hit.get("bm25_score"),
        "flags": [key for key in ("_direct", "_keyword", "_mention", "_graph",
                                    "_relationship_evidence") if hit.get(key)],
    }


def _plan_ref(plan):
    """保留规划决策但移除实体、关键词和改写正文。"""
    if not isinstance(plan, dict):
        return None
    searches = plan.get("search_queries") or []
    return {
        "question_type": plan.get("question_type"),
        "routes": [str(x)[:40] for x in (plan.get("routes") or [])[:10]],
        "needs_graph": bool(plan.get("needs_graph")),
        "planner_method": plan.get("planner_method"),
        "entity_count": len(plan.get("entities") or []),
        "keyword_count": len(plan.get("keywords") or []),
        "search_query_hashes": [query_fingerprint(x) for x in searches[:5]],
    }


class TraceStore:
    def __init__(self, path=TRACE_DB):
        self.path = Path(path)

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, timeout=3)
        try:
            conn.row_factory = sqlite3.Row
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS traces (
                trace_id TEXT PRIMARY KEY, created_at REAL NOT NULL, finished_at REAL,
                status TEXT NOT NULL, query_hash TEXT NOT NULL, query_length INTEGER NOT NULL,
                client_type TEXT NOT NULL, route TEXT, intent TEXT, total_ms REAL,
                generated INTEGER, rejected INTEGER, error_type TEXT,
                code_commit TEXT, index_version TEXT, model TEXT, answer_hash TEXT,
                prompt_versions_json TEXT NOT NULL, stages_json TEXT NOT NULL,
                retrieval_json TEXT NOT NULL, context_json TEXT NOT NULL,
                llm_calls_json TEXT NOT NULL, semantic_plan_json TEXT
            );
            CREATE TABLE IF NOT EXISTS feedback (
                feedback_id TEXT PRIMARY KEY, trace_id TEXT NOT NULL UNIQUE,
                created_at REAL NOT NULL, vote TEXT NOT NULL,
                query TEXT NOT NULL, comment TEXT NOT NULL, client_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending_review', failure_type TEXT,
                observed_answer TEXT NOT NULL DEFAULT '', expected_route TEXT,
                should_refuse INTEGER,
                required_terms_json TEXT NOT NULL DEFAULT '[]',
                acceptable_sources_json TEXT NOT NULL DEFAULT '[]', notes TEXT NOT NULL DEFAULT '',
                FOREIGN KEY(trace_id) REFERENCES traces(trace_id)
            );
            CREATE TABLE IF NOT EXISTS trace_meta (
                key TEXT PRIMARY KEY, value TEXT NOT NULL
            );
            """)
            trace_columns = {row[1] for row in conn.execute("PRAGMA table_info(traces)")}
            if "answer_hash" not in trace_columns:
                conn.execute("ALTER TABLE traces ADD COLUMN answer_hash TEXT")
            feedback_columns = {row[1] for row in conn.execute("PRAGMA table_info(feedback)")}
            if "required_terms_json" not in feedback_columns:
                conn.execute("ALTER TABLE feedback ADD COLUMN required_terms_json TEXT NOT NULL DEFAULT '[]'")
                if "expected_facts_json" in feedback_columns:
                    conn.execute("UPDATE feedback SET required_terms_json=expected_facts_json")
            conn.execute("INSERT OR REPLACE INTO trace_meta(key,value) VALUES ('schema_version',?)",
                         (TRACE_SCHEMA_VERSION,))
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def begin(self, trace):
        with self.connect() as conn:
            conn.execute("""INSERT INTO traces
                (trace_id,created_at,status,query_hash,query_length,client_type,code_commit,
                 index_version,model,prompt_versions_json,stages_json,retrieval_json,
                 context_json,llm_calls_json)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                trace.trace_id, trace.created_at, "running", trace.query_hash,
                trace.query_length, trace.client_type, trace.code_commit,
                trace.index_version, trace.model, _json(PROMPT_VERSIONS), "[]", "[]", "[]", "[]"))

    def finish(self, trace):
        with self.connect() as conn:
            conn.execute("""UPDATE traces SET finished_at=?, status=?, route=?, intent=?, total_ms=?,
                generated=?, rejected=?, error_type=?, stages_json=?, retrieval_json=?, context_json=?,
                llm_calls_json=?, semantic_plan_json=?, answer_hash=? WHERE trace_id=?""", (
                time.time(), trace.status, trace.route, trace.intent, trace.total_ms,
                int(trace.generated), int(trace.rejected), trace.error_type,
                _json(trace.stages), _json(trace.retrieval), _json(trace.context),
                _json(trace.llm_calls), _json(trace.semantic_plan) if trace.semantic_plan else None,
                trace.answer_hash,
                trace.trace_id))

    def submit_feedback(self, trace_id, query, vote, comment, client_type, observed_answer=""):
        with self.connect() as conn:
            trace = conn.execute(
                "SELECT query_hash,client_type,answer_hash FROM traces WHERE trace_id=?", (trace_id,)).fetchone()
            if not trace:
                raise ValueError("trace_not_found")
            if trace["query_hash"] != query_fingerprint(query):
                raise ValueError("query_mismatch")
            if trace["client_type"] != client_type:
                raise ValueError("client_mismatch")
            if not trace["answer_hash"] or trace["answer_hash"] != content_fingerprint(observed_answer):
                raise ValueError("answer_mismatch")
            existing = conn.execute("SELECT * FROM feedback WHERE trace_id=?", (trace_id,)).fetchone()
            if existing:
                if (existing["vote"] == vote and existing["query"] == query and
                        existing["comment"] == comment and existing["client_type"] == client_type and
                        existing["observed_answer"] == observed_answer):
                    return {"feedback_id": existing["feedback_id"], "status": existing["status"],
                            "idempotent": True}
                raise ValueError("already_submitted")
            feedback_id = uuid.uuid4().hex
            try:
                conn.execute("""INSERT INTO feedback
                    (feedback_id,trace_id,created_at,vote,query,comment,client_type,observed_answer)
                    VALUES (?,?,?,?,?,?,?,?)""", (
                    feedback_id, trace_id, time.time(), vote, query, comment, client_type,
                    observed_answer))
            except sqlite3.IntegrityError as exc:
                raise ValueError("already_submitted") from exc
            return {"feedback_id": feedback_id, "status": "pending_review"}

    def get_trace(self, trace_id):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM traces WHERE trace_id=?", (trace_id,)).fetchone()
            return dict(row) if row else None


class RAGTrace:
    def __init__(self, query, client_type="other", store=None, code_commit="", index_version=""):
        from llm_client import llm
        self.trace_id = uuid.uuid4().hex
        self.created_at = time.time()
        self.started = time.perf_counter()
        self.query_hash = query_fingerprint(query)
        self.query_length = len(query)
        self.client_type = client_type
        self.store = store or trace_store
        self.code_commit = code_commit
        self.index_version = index_version
        self.model = llm.model
        self.stages, self.retrieval, self.context, self.llm_calls = [], [], [], []
        self.semantic_plan = None
        self.answer_hash = None
        self.status, self.route, self.intent, self.error_type = "running", None, None, None
        self.generated = self.rejected = False
        self.total_ms = None
        self._active_stage = None
        self.store.begin(self)

    @contextmanager
    def span(self, name):
        started = time.perf_counter()
        previous, self._active_stage = self._active_stage, name
        event = {"name": name}
        try:
            yield
            event["status"] = "ok"
        except Exception as exc:
            event.update(status="error", error=type(exc).__name__)
            raise
        finally:
            event["elapsed_ms"] = round((time.perf_counter() - started) * 1000, 2)
            self.stages.append(event)
            self._active_stage = previous

    def record_retrieval(self, channel, hits, query=None):
        self.retrieval.append({
            "channel": channel,
            "query_hash": query_fingerprint(query) if query else None,
            "hits": [_hit_ref(hit, rank) for rank, hit in enumerate(hits, 1)],
        })

    def record_llm_event(self, event):
        safe = {key: event.get(key) for key in (
            "status", "model", "attempt", "elapsed_ms", "prompt_tokens",
            "completion_tokens", "total_tokens", "error_type")}
        safe["stage"] = self._active_stage or "unknown"
        self.llm_calls.append(safe)

    def finish(self, result=None, error=None):
        result = result or {}
        self.total_ms = round((time.perf_counter() - self.started) * 1000, 2)
        self.status = "error" if error else "ok"
        self.error_type = type(error).__name__ if error else None
        self.route = result.get("route_used")
        self.intent = result.get("intent")
        self.generated = bool(result.get("answer"))
        self.rejected = bool(result.get("rejected"))
        self.semantic_plan = _plan_ref(result.get("semantic_plan"))
        self.context = [_hit_ref(hit, rank) for rank, hit in enumerate(result.get("hits") or [], 1)]
        self.answer_hash = content_fingerprint(feedback_snapshot(result))
        self.store.finish(self)


trace_store = TraceStore()
