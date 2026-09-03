# -*- coding: utf-8 -*-
"""ask_stream / /api/ask/stream / prepare_generation 的离线测试。

不加载向量模型、不调用真实 LLM；llm 全部走 mock，保证回归测试零成本可复现。
"""
import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("RAG_PREWARM", "0")

from fastapi.testclient import TestClient  # noqa: E402
import httpx  # noqa: E402

from scripts import api_security, api_server, rag_ask  # noqa: E402
from scripts.llm_client import LLMClient  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def hit(name="重息壤", category="物品", item_id="x1", text="描述文本", vector_sim=0.9, **flags):
    return {"meta": {"name": name, "category": category, "item_id": item_id, "chunk_index": 0},
            "text": text, "score": vector_sim, "vector_sim": vector_sim,
            "bm25_score": 0.0, **flags}


class _StubLLM:
    """替换 rag_ask.llm 全局引用的离线桩（避免双份模块加载导致的单例 patch 失效）。"""

    def __init__(self, available=True, chat_reply=None, stream_parts=(), chat_error=None):
        self.available_flag = available
        self.chat_reply = chat_reply
        self.chat_error = chat_error
        self.stream_parts = list(stream_parts)
        self.calls = {"chat": [], "chat_stream": []}

    def available(self):
        return self.available_flag

    def chat(self, *args, **kwargs):
        self.calls["chat"].append((args, kwargs))
        if self.chat_error is not None:
            raise self.chat_error
        return self.chat_reply

    def chat_stream(self, *args, **kwargs):
        self.calls["chat_stream"].append((args, kwargs))
        abort = kwargs.get("abort")
        if abort is not None and getattr(abort, "is_set", lambda: False)():
            raise RuntimeError("mock abort: 客户端已断开")
        if self.chat_error is not None:
            raise self.chat_error
        return iter(self.stream_parts)


def _use_llm(**kwargs):
    """以 rag_ask.llm 全局引用为目标打桩，返回 (stub, patcher)。"""
    stub = _StubLLM(**kwargs)
    patcher = patch.object(rag_ask, "llm", stub)
    patcher.start()
    return stub, patcher


def _fake_stream(*_args, **_kwargs):
    """默认 chat_stream：产出两段文本。"""
    return iter(["第一段。", "第二段。"])


class PrepareGenerationTests(unittest.TestCase):
    def test_no_llm_returns_no_llm_kind(self):
        stub, p = _use_llm(available=False)
        try:
            self.assertEqual(rag_ask.prepare_generation("重息壤是什么", [hit()])["kind"], "no_llm")
        finally:
            p.stop()

    def test_empty_hits_rejects_without_hits(self):
        stub, p = _use_llm()
        try:
            prep = rag_ask.prepare_generation("重息壤是什么", [])
        finally:
            p.stop()
        self.assertEqual(prep["kind"], "reject")
        self.assertTrue(prep["rejected"])
        self.assertEqual(prep["hits"], [])

    def test_low_similarity_rejects(self):
        hits = [hit(vector_sim=0.1)]
        stub, p = _use_llm()
        try:
            prep = rag_ask.prepare_generation("重息壤是什么", hits)
        finally:
            p.stop()
        self.assertEqual(prep["kind"], "reject")
        self.assertEqual(prep["hits"], hits[:1])

    def test_direct_hit_bypasses_vector_threshold(self):
        hits = [hit(vector_sim=0.1, _direct=True)]
        stub, p = _use_llm()
        try:
            prep = rag_ask.prepare_generation("重息壤是什么", hits, top_k=1)
        finally:
            p.stop()
        self.assertEqual(prep["kind"], "prompt")
        self.assertIn("重息壤是什么", prep["prompt"])
        self.assertIn("资料", prep["prompt"])
        self.assertEqual(len(prep["sources"]), 1)

    def test_curated_mention_bypasses_vector_threshold(self):
        hits = [hit(vector_sim=0.1, _mention=True)]
        stub, p = _use_llm()
        try:
            kind = rag_ask.prepare_generation("谁提到了它", hits)["kind"]
        finally:
            p.stop()
        self.assertEqual(kind, "prompt")

    def test_gen_answer_non_stream_parity(self):
        stub, p = _use_llm(chat_reply="答案文本")
        try:
            out = rag_ask.gen_answer("重息壤是什么", [hit()], top_k=1)
        finally:
            p.stop()
        self.assertEqual(out["answer"], "答案文本")
        self.assertFalse(out["rejected"])
        self.assertEqual(out["sources"][0]["name"], "重息壤")
        self.assertEqual(stub.calls["chat"][0][1]["max_tokens"], rag_ask.GEN_ANSWER_MAX_TOKENS)


class AskStreamTests(unittest.TestCase):
    def _rag_result(self, hits):
        return {"ok": True, "intent": "知识", "method": "rule",
                "route_used": "rag", "hits": hits}

    def test_rag_route_streams_meta_delta_done(self):
        stub, p = _use_llm(stream_parts=["第一段。", "第二段。"])
        ask_p = patch.object(rag_ask, "ask", return_value=self._rag_result([hit("甲"), hit("乙")]))
        ask_p.start()
        try:
            events = list(rag_ask.ask_stream("重息壤是什么", top_k=2, gen_answer=True))
        finally:
            ask_p.stop()
            p.stop()
        self.assertEqual([e["event"] for e in events],
                         ["phase", "meta", "delta", "delta", "done"])
        done = events[-1]["data"]
        self.assertEqual(done["answer"], "第一段。第二段。")
        self.assertFalse(done["rejected"])
        self.assertEqual([s["name"] for s in done["sources"]], ["甲", "乙"])
        # meta 与 done 的来源一致：前端可在首字到达前先展示来源
        self.assertEqual(events[1]["data"]["sources"], done["sources"])

    def test_structured_route_done_without_generation(self):
        structured = {"ok": True, "route_used": "structured", "route": "recipe",
                      "item": "重息壤", "recipes": []}
        ask_p = patch.object(rag_ask, "ask", return_value=structured)
        ask_p.start()
        try:
            events = list(rag_ask.ask_stream("重息壤怎么造", gen_answer=True))
        finally:
            ask_p.stop()
        self.assertEqual([e["event"] for e in events], ["phase", "done"])

    def test_no_llm_skips_generation(self):
        stub, p = _use_llm(available=False)
        ask_p = patch.object(rag_ask, "ask", return_value=self._rag_result([hit()]))
        ask_p.start()
        try:
            events = list(rag_ask.ask_stream("重息壤是什么", top_k=1, gen_answer=True))
        finally:
            ask_p.stop()
            p.stop()
        self.assertEqual([e["event"] for e in events], ["phase", "done"])
        self.assertNotIn("answer", events[-1]["data"])

    def test_reject_low_similarity_no_stream_call(self):
        stub, p = _use_llm(stream_parts=["不应出现"])
        ask_p = patch.object(rag_ask, "ask",
                             return_value=self._rag_result([hit(vector_sim=0.1)]))
        ask_p.start()
        try:
            events = list(rag_ask.ask_stream("胡问一句", top_k=1, gen_answer=True))
        finally:
            ask_p.stop()
            p.stop()
        self.assertEqual([e["event"] for e in events], ["phase", "done"])
        self.assertTrue(events[-1]["data"]["rejected"])
        self.assertIn("未找到足够相关", events[-1]["data"]["answer"])
        self.assertEqual(stub.calls["chat_stream"], [], "拒答不应调用生成")

    def test_gen_answer_disabled_returns_done_only(self):
        stub, p = _use_llm(stream_parts=["x"])
        ask_p = patch.object(rag_ask, "ask", return_value=self._rag_result([hit()]))
        ask_p.start()
        try:
            events = list(rag_ask.ask_stream("重息壤是什么", top_k=1, gen_answer=False))
        finally:
            ask_p.stop()
            p.stop()
        self.assertEqual([e["event"] for e in events], ["phase", "done"])

    def test_enum_route_returns_complete_deterministic_answer(self):
        enum_result = {"ok": True, "intent": "枚举", "method": "rule", "route_used": "enum",
                       "enum": {"label": "主线任务", "category": "任务",
                                "names": ["序章", "第一章"]},
                       "names": ["序章", "第一章"], "count": 2}
        stub, p = _use_llm(available=False)
        ask_p = patch.object(rag_ask, "ask", return_value=enum_result)
        ask_p.start()
        try:
            events = list(rag_ask.ask_stream("有哪些主线任务", gen_answer=True))
        finally:
            ask_p.stop()
            p.stop()
        self.assertEqual([e["event"] for e in events], ["phase", "done"])
        self.assertIn("共找到 2 个主线任务", events[-1]["data"]["answer"])
        self.assertIn("2. 第一章", events[-1]["data"]["answer"])
        self.assertEqual(events[-1]["data"]["route_used"], "enum")
        self.assertEqual(stub.calls["chat_stream"], [])

    def test_preset_abort_stops_without_delta(self):
        stub, p = _use_llm(stream_parts=["x"])
        ask_p = patch.object(rag_ask, "ask", return_value=self._rag_result([hit()]))
        ask_p.start()
        stop = threading.Event()
        stop.set()  # 模拟客户端已断开
        try:
            events = list(rag_ask.ask_stream("重息壤是什么", top_k=1, gen_answer=True,
                                             abort=stop))
        finally:
            ask_p.stop()
            p.stop()
        self.assertEqual([e["event"] for e in events], ["phase", "meta", "done"])
        self.assertNotIn("answer", events[-1]["data"])

    def test_error_after_delta_is_not_followed_by_done(self):
        stub, p = _use_llm()

        def broken_stream(*_args, **_kwargs):
            yield "半截回答"
            raise RuntimeError("mock stream disconnected")

        stub.chat_stream = broken_stream
        ask_p = patch.object(rag_ask, "ask", return_value=self._rag_result([hit()]))
        ask_p.start()
        try:
            it = rag_ask.ask_stream("重息壤是什么", top_k=1, gen_answer=True)
            with self.assertRaisesRegex(RuntimeError, "disconnected"):
                list(it)
        finally:
            ask_p.stop()
            p.stop()


class LLMClientStreamTests(unittest.TestCase):
    def test_non_stream_continues_when_provider_reports_length(self):
        client = LLMClient()
        first = {"choices": [{"message": {"content": "前半段"}, "finish_reason": "length"}]}
        second = {"choices": [{"message": {"content": "后半段"}, "finish_reason": "stop"}]}
        with patch.object(client, "_chat_completions", side_effect=[first, second]) as call:
            answer = client.chat("问题", max_tokens=800)
        self.assertEqual(answer, "前半段后半段")
        self.assertEqual(call.call_count, 2)
        continued_messages = call.call_args_list[1].args[0]
        self.assertEqual(continued_messages[-2]["role"], "assistant")
        self.assertIn("截断处继续", continued_messages[-1]["content"])

    def test_non_stream_expands_budget_when_length_has_no_body(self):
        client = LLMClient()
        first = {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
        second = {"choices": [{"message": {"content": "完整正文"}, "finish_reason": "stop"}]}
        with patch.object(client, "_chat_completions", side_effect=[first, second]) as call:
            answer = client.chat("问题", max_tokens=800)
        self.assertEqual(answer, "完整正文")
        self.assertEqual(call.call_args_list[0].kwargs["max_tokens"], 800)
        self.assertEqual(call.call_args_list[1].kwargs["max_tokens"], 1600)
        self.assertEqual(call.call_args_list[1].args[0], call.call_args_list[0].args[0])

    def test_stream_continues_when_provider_reports_length(self):
        responses = [
            [
                'data: {"choices":[{"delta":{"content":"前半段"},"finish_reason":null}]}',
                'data: {"choices":[{"delta":{},"finish_reason":"length"}]}',
                "data: [DONE]",
            ],
            [
                'data: {"choices":[{"delta":{"content":"后半段"},"finish_reason":null}]}',
                'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}',
                "data: [DONE]",
            ],
        ]

        class Response:
            status_code = 200
            def __init__(self, lines): self.lines = lines
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def iter_lines(self): return iter(self.lines)

        class Client:
            def __init__(self, *_args, **_kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def stream(self, *_args, **_kwargs): return Response(responses.pop(0))

        client = LLMClient()
        client.api_key = "test-only"
        with patch("scripts.llm_client.httpx.Client", Client):
            answer = "".join(client.chat_stream("问题", max_tokens=800))
        self.assertEqual(answer, "前半段后半段")
        self.assertEqual(responses, [])

    def test_preset_abort_does_not_open_or_retry_request(self):
        client = LLMClient()
        client.api_key = "test-only"
        stop = threading.Event()
        stop.set()
        with patch("scripts.llm_client.httpx.Client", MagicMock()) as http_client, \
                patch("scripts.llm_client.time.sleep") as sleep:
            with self.assertRaisesRegex(RuntimeError, "已中止"):
                list(client.chat_stream("问题", abort=stop))
        http_client.assert_not_called()
        sleep.assert_not_called()

    def test_network_error_after_delta_is_not_retried(self):
        calls = []

        class BrokenResponse:
            status_code = 200

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def iter_lines(self):
                yield 'data: {"choices":[{"delta":{"content":"半截"}}]}'
                raise httpx.ReadError("mock disconnected")

        class FakeClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def stream(self, *_args, **_kwargs):
                calls.append(1)
                return BrokenResponse()

        client = LLMClient()
        client.api_key = "test-only"
        with patch("scripts.llm_client.httpx.Client", FakeClient), \
                patch("scripts.llm_client.time.sleep") as sleep:
            stream = client.chat_stream("问题")
            self.assertEqual(next(stream), "半截")
            with self.assertRaisesRegex(RuntimeError, "ReadError"):
                next(stream)
        self.assertEqual(len(calls), 1)
        sleep.assert_not_called()


class AskStreamHttpTests(unittest.TestCase):
    def setUp(self):
        # 沙箱下 tempfile 目录对 sqlite 不友好 → 额度库直接用 workspace logs 下的固定文件，
        # tearDown 尽力删除；残留也不影响后续运行。
        logs_dir = ROOT / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        self.db = logs_dir / f"ask-stream-budget-{os.getpid()}-{id(self)}.sqlite3"
        self.budget = api_security.AskBudget(self.db, per_minute=100)
        self.addCleanup(self._cleanup_db)
        for patcher in (
            patch.object(api_security, "ASK_BUDGET", self.budget),
            patch.object(api_security, "API_ACCESS_TOKEN", ""),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def _cleanup_db(self):
        try:
            self.db.unlink(missing_ok=True)
        except OSError:
            pass

    def _canned_stream(self, *_args, **_kwargs):
        yield {"event": "phase", "data": {"stage": "route", "text": "检索中"}}
        yield {"event": "meta", "data": {"ok": True, "route_used": "rag", "intent": "知识", "sources": []}}
        yield {"event": "delta", "data": {"text": "你好"}}
        yield {"event": "done", "data": {"ok": True, "route_used": "rag", "intent": "知识",
                                         "answer": "你好", "rejected": False, "sources": []}}

    def test_sse_event_frame_and_done_payload(self):
        with patch("rag_ask.ask_stream", side_effect=self._canned_stream), \
                TestClient(api_server.app) as client:
            resp = client.post("/api/ask/stream",
                               json={"query": "重息壤是什么", "top_k": 2, "client_type": "web"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.headers["content-type"].startswith("text/event-stream"))
        self.assertEqual(resp.headers.get("x-accel-buffering"), "no")
        self.assertRegex(resp.headers.get("x-trace-id", ""), r"^[0-9a-f]{32}$")
        body = resp.text
        for tag in ("event: phase", "event: meta", "event: delta", "event: done"):
            self.assertIn(tag, body)
        done_block = body.split("event: done\ndata: ", 1)[1].split("\n\n", 1)[0]
        done = json.loads(done_block)
        self.assertEqual(done["answer"], "你好")
        self.assertIn("trace_id", done)
        self.assertIn("feedback_snapshot", done)

    def test_busy_returns_429_before_stream(self):
        with patch("rag_ask.ask_stream", side_effect=self._canned_stream), \
                TestClient(api_server.app) as client:
            sem = api_server._ASK_SEMAPHORE
            held = []
            while sem.acquire(blocking=False):
                held.append(True)  # 占满全部并发名额
            try:
                resp = client.post("/api/ask/stream", json={"query": "重息壤是什么"})
            finally:
                for _ in held:
                    sem.release()
        self.assertEqual(resp.status_code, 429)
        self.assertEqual(resp.headers["retry-after"], "3")

    def test_semaphore_released_after_stream(self):
        with patch("rag_ask.ask_stream", side_effect=self._canned_stream), \
                TestClient(api_server.app) as client:
            resp = client.post("/api/ask/stream", json={"query": "重息壤是什么"})
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(api_server._ASK_SEMAPHORE.acquire(blocking=False))
        api_server._ASK_SEMAPHORE.release()

    def test_partial_generation_failure_emits_error_without_done(self):
        def broken_stream(*_args, **_kwargs):
            yield {"event": "delta", "data": {"text": "半截回答"}}
            raise RuntimeError("mock stream disconnected")

        with patch("rag_ask.ask_stream", side_effect=broken_stream), \
                TestClient(api_server.app) as client:
            resp = client.post("/api/ask/stream", json={"query": "重息壤是什么"})
        self.assertEqual(resp.status_code, 200)
        self.assertIn("event: delta", resp.text)
        self.assertIn("event: error", resp.text)
        self.assertNotIn("event: done", resp.text)
        self.assertTrue(api_server._ASK_SEMAPHORE.acquire(blocking=False))
        api_server._ASK_SEMAPHORE.release()


if __name__ == "__main__":
    unittest.main()
