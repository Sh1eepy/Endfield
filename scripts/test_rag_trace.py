"""Trace、反馈隔离、LLM usage 与 Replay 归因的离线测试。"""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from fastapi.testclient import TestClient

os.environ.setdefault("HF_HUB_OFFLINE", "1")
from scripts import api_security, api_server, eval_answers, eval_case, llm_client, rag_trace, replay_bad_cases
from scripts import build_eval_manifest, rag_config, rag_prompts


class TraceStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="endfield-trace-")
        self.addCleanup(self.tmp.cleanup)
        self.store = rag_trace.TraceStore(Path(self.tmp.name) / "trace.sqlite3")

    def trace(self, query="莱万汀喜欢吃什么"):
        return rag_trace.RAGTrace(query, "web", store=self.store,
                                  code_commit="test", index_version="index-test")

    def test_ordinary_trace_never_stores_query_text(self):
        trace = self.trace()
        with trace.span("intent_classify"):
            pass
        trace.record_retrieval("rrf", [{"meta": {"name": "莱万汀", "category": "干员",
            "item_id": "1", "chunk_index": 0}, "score": .1}], "莱万汀喜欢吃什么")
        trace.record_llm_event({"status": "ok", "model": "mock", "attempt": 1,
                                "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
        trace.finish({"route_used": "rag", "intent": "偏好", "answer": "冰淇淋", "hits": [],
                      "semantic_plan": {"question_type": "preference", "entities": ["莱万汀"],
                          "keywords": ["冰淇淋"], "search_queries": ["莱万汀 冰淇淋"],
                          "routes": ["rag"], "planner_method": "llm"}})
        row = self.store.get_trace(trace.trace_id)
        self.assertEqual(row["query_hash"], rag_trace.query_fingerprint("莱万汀喜欢吃什么"))
        self.assertNotIn("莱万汀喜欢吃什么", json.dumps(row, ensure_ascii=False))
        self.assertEqual(json.loads(row["llm_calls_json"])[0]["total_tokens"], 15)
        with self.store.connect() as conn:
            columns = {x[1] for x in conn.execute("PRAGMA table_info(traces)")}
        self.assertNotIn("query", columns)

    def test_feedback_requires_matching_trace_and_is_quarantined(self):
        trace = self.trace(); trace.finish({"route_used": "rag", "feedback_snapshot": "旧回答"})
        saved = self.store.submit_feedback(trace.trace_id, "莱万汀喜欢吃什么", "not_useful",
                                           "漏掉语音", "web", "旧回答")
        self.assertEqual(saved["status"], "pending_review")
        with self.store.connect() as conn:
            row = conn.execute("SELECT * FROM feedback").fetchone()
        self.assertEqual(row["query"], "莱万汀喜欢吃什么")
        self.assertEqual(row["observed_answer"], "旧回答")
        repeated = self.store.submit_feedback(trace.trace_id, "莱万汀喜欢吃什么", "not_useful",
                                              "漏掉语音", "web", "旧回答")
        self.assertTrue(repeated["idempotent"])
        with self.assertRaisesRegex(ValueError, "already_submitted"):
            self.store.submit_feedback(trace.trace_id, "莱万汀喜欢吃什么", "useful", "", "web", "旧回答")
        with self.assertRaisesRegex(ValueError, "client_mismatch"):
            self.store.submit_feedback(trace.trace_id, "莱万汀喜欢吃什么", "useful", "", "miniprogram", "旧回答")
        other = self.trace("佩丽卡怎么玩"); other.finish({"feedback_snapshot": "回答"})
        with self.assertRaisesRegex(ValueError, "query_mismatch"):
            self.store.submit_feedback(other.trace_id, "被篡改的问题", "not_useful", "", "web", "回答")
        with self.assertRaisesRegex(ValueError, "answer_mismatch"):
            self.store.submit_feedback(other.trace_id, "佩丽卡怎么玩", "not_useful", "", "web", "伪造回答")


class LLMUsageTests(unittest.TestCase):
    def test_usage_is_observed_without_changing_chat_return_type(self):
        events = []

        def handler(request):
            return httpx.Response(200, json={"model": "mock-model", "choices": [{
                "message": {"content": "回答"}}], "usage": {
                "prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14}})

        client = httpx.Client(transport=httpx.MockTransport(handler))
        instance = llm_client.LLMClient(); instance.api_key = "mock-key"
        with patch("httpx.Client", return_value=client), llm_client.observe_llm(events.append):
            answer = instance.chat("测试")
        self.assertEqual(answer, "回答")
        self.assertEqual(events[0]["total_tokens"], 14)
        self.assertEqual(events[0]["model"], "mock-model")

    def test_final_server_error_is_not_labeled_as_retry(self):
        events = []

        def handler(request):
            return httpx.Response(503, text="unavailable")

        client = httpx.Client(transport=httpx.MockTransport(handler))
        instance = llm_client.LLMClient(); instance.api_key = "mock-key"; instance.max_retries = 0
        with patch("httpx.Client", return_value=client), llm_client.observe_llm(events.append):
            with self.assertRaises(RuntimeError):
                instance.chat("测试")
        self.assertEqual(events[-1]["status"], "error")
        self.assertEqual(events[-1]["error_type"], "HTTP_503")

    def test_judge_prompt_is_versioned_file(self):
        system, suffix = eval_answers.load_judge_prompt()
        self.assertIn("RAG", system)
        self.assertIn("faithfulness", suffix)
        self.assertRegex(eval_answers.JUDGE_PROMPT_VERSION, r"^sha256:[0-9a-f]{16}$")

    def test_manifest_uses_runtime_config_and_prompt_single_source(self):
        manifest = build_eval_manifest.build_manifest()
        self.assertNotIn("runtime:", json.dumps(manifest))
        self.assertNotIn("llm_model", manifest)
        self.assertEqual(manifest["embedding_model"], rag_config.EMBEDDING_MODEL)
        self.assertEqual(manifest["prompt_versions"], rag_prompts.PROMPT_VERSIONS)
        self.assertEqual(manifest["retrieval"], rag_config.retrieval_config())
        self.assertEqual(build_eval_manifest.evaluation_metadata()["llm_model"],
                         llm_client.llm.model)


class TraceHttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="endfield-trace-http-")
        self.addCleanup(self.tmp.cleanup)
        self.store = rag_trace.TraceStore(Path(self.tmp.name) / "trace.sqlite3")
        self.budget = api_security.AskBudget(Path(self.tmp.name) / "budget.sqlite3",
                                             per_minute=100, per_ip_day=100, per_day=100)
        for patcher in (patch.object(rag_trace, "trace_store", self.store),
                        patch.object(api_security, "ASK_BUDGET", self.budget),
                        patch.object(api_security, "FEEDBACK_BUDGET", self.budget),
                        patch.object(api_security, "API_ACCESS_TOKEN", "")):
            patcher.start(); self.addCleanup(patcher.stop)

    def test_http_trace_header_body_and_feedback(self):
        def fake_ask(query, top_k, gen_answer_, trace):
            with trace.span("fake_retrieval"):
                trace.record_retrieval("rrf", [], query)
            return {"ok": True, "route_used": "rag", "answer": "测试回答", "hits": []}

        with TestClient(api_server.app) as client, patch("rag_ask.ask", side_effect=fake_ask):
            answer = client.post("/api/ask", json={"query": "测试", "client_type": "web"})
            self.assertEqual(answer.status_code, 200)
            trace_id = answer.json()["trace_id"]
            self.assertEqual(answer.headers["x-trace-id"], trace_id)
            feedback = client.post("/api/feedback", json={
                "trace_id": trace_id, "query": "测试", "vote": "not_useful",
                "observed_answer": "测试回答", "client_type": "web"})
            self.assertEqual(feedback.status_code, 201)
            self.assertEqual(feedback.json()["status"], "pending_review")
            self.assertEqual(client.post("/api/feedback", json={
                "trace_id": trace_id, "query": "测试", "vote": "not_useful",
                "observed_answer": "测试回答", "client_type": "web"}).status_code, 201)
            self.assertEqual(client.post("/api/feedback", json={
                "trace_id": trace_id, "query": "篡改", "vote": "useful",
                "observed_answer": "测试回答", "client_type": "web"}).status_code, 400)
        row = self.store.get_trace(trace_id)
        self.assertEqual(row["status"], "ok")
        self.assertEqual(json.loads(row["stages_json"])[0]["name"], "fake_retrieval")

    def test_trace_store_failure_does_not_break_answer(self):
        broken = rag_trace.TraceStore(Path(self.tmp.name))
        with patch.object(rag_trace, "trace_store", broken), TestClient(api_server.app) as client:
            with patch("rag_ask.ask", return_value={"ok": True, "route_used": "structured"}):
                response = client.post("/api/ask", json={"query": "测试"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("trace_id", response.json())


class AttributionTests(unittest.TestCase):
    def case(self, **updates):
        row = {"query": "测试", "expected_route": "rag", "should_refuse": 0,
               "acceptable_sources_json": "[]", "required_terms_json": "[]"}
        row.update(updates)
        return eval_case.EvaluationCase.from_mapping(row)

    def test_route_graph_generation_and_fixed_attributions(self):
        self.assertEqual(replay_bad_cases.analyze_pipeline(
            self.case(expected_route=None), {"route_used": "rag"})["code"], "GOLD_ROUTE_MISSING")
        self.assertEqual(replay_bad_cases.analyze_pipeline(
            self.case(), {"route_used": "graph"})["code"], "ROUTE_WRONG")
        self.assertEqual(replay_bad_cases.analyze_pipeline(
            self.case(expected_route="graph"), {"route_used": "rag", "graph": {}})["code"],
            "GRAPH_MISSING")
        incomplete = replay_bad_cases.analyze_answer(
            self.case(required_terms_json='["冰淇淋"]'),
            {"route_used": "rag", "answer": "不知道", "sources": []})
        self.assertEqual(incomplete["code"], "GENERATION_INCOMPLETE")
        fixed = replay_bad_cases.analyze_answer(
            self.case(required_terms_json='["冰淇淋"]'),
            {"route_used": "rag", "answer": "喜欢冰淇淋 [来源1]", "sources": []})
        self.assertEqual(fixed["status"], "passed")

    def test_retrieval_layer_has_no_fake_route_and_stops_waterfall(self):
        trace = type("T", (), {"retrieval": []})()
        layers = replay_bad_cases.waterfall(
            self.case(acceptable_sources_json='["不存在来源"]'), {"hits": []}, trace, "answer")
        self.assertEqual(list(layers), ["retrieval"])
        self.assertEqual(layers["retrieval"]["status"], "failed")


if __name__ == "__main__":
    unittest.main()
