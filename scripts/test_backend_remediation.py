"""Offline regressions for entity, stream termination and incremental index fixes."""
import os
import sqlite3
import time
import unittest
from unittest.mock import MagicMock, patch

os.environ["LLM_API_KEY"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
from scripts import rag_ask
from scripts import api_server
from scripts import build_eval_manifest, eval_answers
from scripts.build_knowledge_graph import (GraphBuilder, content_hash as graph_content_hash,
                                           create_schema)
from scripts.build_rag import diff_chunks
from scripts.llm_client import LLMClient
from scripts.rag_search import RAGRetriever


class EntityTests(unittest.TestCase):
    def test_full_entity_names_are_not_truncated(self):
        kb = {name: {"category": "test"} for name in
              ("诀", "诀的信物", "重息壤", "息壤", "佩丽卡")}
        for query, expected in (("重息壤是什么", "重息壤"),
                                ("诀的信物是什么", "诀的信物"),
                                ("诀升级材料", "诀"), ("佩丽卡怎么培养", "佩丽卡")):
            with self.subTest(query=query), patch.object(rag_ask, "_get_kb_names", return_value=kb):
                self.assertEqual(rag_ask.extract_kb_entity(query)[0], expected)

    def test_direct_hit_keeps_source_item_id(self):
        kb = {"佩丽卡": {"item_id": "42", "category": "干员", "full_text": "正文"}}
        with patch.object(rag_ask, "_get_kb_names", return_value=kb):
            self.assertEqual(rag_ask.kb_direct_hits("佩丽卡是谁")[0]["meta"]["item_id"], "42")

    def test_direct_entity_query_does_not_run_duplicate_hybrid_search(self):
        kb = {"佩丽卡": {"item_id": "42", "category": "干员", "full_text": "正文"}}
        retriever = MagicMock()
        retriever.search.return_value = []
        with patch.object(rag_ask, "_get_kb_names", return_value=kb), \
                patch.object(rag_ask, "_get_retriever", return_value=retriever):
            result = rag_ask.rag_search("佩丽卡是谁")
        self.assertEqual(retriever.search.call_count, 1)
        self.assertEqual(result[0]["meta"]["name"], "佩丽卡")

    def test_multi_search_merges_distinct_chunks_from_one_source(self):
        meta = {"name": "条目", "category": "档案", "item_id": "7"}
        hits = [[{"meta": dict(meta, chunk_index=0), "text": "第一段证据", "score": .2}],
                [{"meta": dict(meta, chunk_index=1), "text": "第二段证据", "score": .3}]]
        plan = {"routes": ["rag"], "search_queries": ["原问题", "补充查询"]}
        with patch.object(rag_ask, "rag_search", side_effect=hits):
            result = rag_ask.multi_search("原问题", plan=plan)
        self.assertEqual(len(result), 1)
        self.assertIn("第一段证据", result[0]["text"])
        self.assertIn("第二段证据", result[0]["text"])
        self.assertEqual(result[0]["score"], .3)

    def test_spoken_suffix_and_duplicate_chunks_do_not_hide_item(self):
        retriever = RAGRetriever.__new__(RAGRetriever)
        retriever.metas = [
            {"name": "更换装备", "category": "语音", "item_id": "1", "chunk_index": 0},
            {"name": "紫晶装备原件", "category": "物品", "item_id": "2", "chunk_index": 0},
            {"name": "紫晶装备原件", "category": "物品", "item_id": "2", "chunk_index": 1},
        ]
        names = [retriever.metas[i]["name"] for i, _ in
                 retriever.name_search("紫晶装备怎么弄", 5)]
        self.assertEqual(names[0], "紫晶装备原件")
        self.assertEqual(names.count("紫晶装备原件"), 1)


class IndexTests(unittest.TestCase):
    def test_shrinking_and_resplitting_removes_old_tail(self):
        old = [{"id": "a-0", "text": "abc", "hash": "same"},
               {"id": "a-1", "text": "def", "hash": "same"}]
        new = [{"id": "a-0", "text": "abcdef", "hash": "same"}]
        self.assertEqual(diff_chunks(old, new), (["a-0"], ["a-1"]))
        self.assertEqual(diff_chunks(new, new), ([], []))
        self.assertEqual(diff_chunks(old, []), ([], ["a-0", "a-1"]))

    def test_graph_hash_covers_structured_and_operator_inputs(self):
        row = {"name": "测试", "category": "干员", "full_text": "正文",
               "sections_struct": {"身份": [{"text": "A"}]}}
        base = graph_content_hash(row, {"faction": "组织甲"})
        changed_section = dict(row, sections_struct={"身份": [{"text": "B"}]})
        self.assertNotEqual(base, graph_content_hash(changed_section, {"faction": "组织甲"}))
        self.assertNotEqual(base, graph_content_hash(row, {"faction": "组织乙"}))

    def test_graph_entity_update_preserves_existing_relations(self):
        con = sqlite3.connect(":memory:")
        con.execute("PRAGMA foreign_keys=ON")
        create_schema(con)
        rows = [{"item_id": "1", "name": "甲", "category": "干员"},
                {"item_id": "2", "name": "乙", "category": "干员"}]
        builder = GraphBuilder(con, rows)
        builder.ensure_source_entities()
        builder.add_relation("kb:1", "REFERENCES", "kb:2", "1", "甲提到乙")
        builder.rows[0]["name"] = "甲改名"
        builder.ensure_source_entities()
        self.assertEqual(con.execute("SELECT COUNT(*) FROM relations").fetchone()[0], 1)
        con.close()


class ApiBoundaryTests(unittest.TestCase):
    def test_synthesis_resource_limits_are_enforced(self):
        self.assertFalse(api_server.synthesis("x" * 301)["ok"])
        self.assertFalse(api_server.synthesis("重息壤", max_depth=11)["ok"])


class EvaluationTests(unittest.TestCase):
    def test_manifest_versions_retrieval_implementation(self):
        manifest = build_eval_manifest.build_manifest()
        self.assertEqual(manifest["schema_version"], 3)
        self.assertIn("scripts/rag_ask.py", manifest["implementation"])

    def test_judge_receives_retrieved_text_and_source_identity(self):
        result = {"hits": [{"meta": {"name": "条目", "category": "档案", "item_id": "7"},
                            "text": "可核查原文", "score": 1.0}]}
        self.assertEqual(eval_answers.judge_evidence(result)[0], {
            "name": "条目", "category": "档案", "item_id": "7", "text": "可核查原文"})

    def test_explicit_rejection_field_wins_over_answer_wording(self):
        from scripts.eval_case import deterministic_score
        case = {"query": "test", "should_refuse": False}
        result = {"rejected": False, "answer": "现有资料不足以判断后续版本。"}
        self.assertTrue(deterministic_score(case, result)["refusal_correct"])

    def test_legacy_refusal_requires_exact_canonical_answer(self):
        from scripts.eval_case import deterministic_score
        case = {"query": "test", "should_refuse": True}
        canonical = {"answer": "知识库中未找到足够相关的资料来回答这个问题。"}
        incidental = {"answer": "没有找到该道具，但资料足以回答其他部分。"}
        self.assertTrue(deterministic_score(case, canonical)["refusal_correct"])
        self.assertFalse(deterministic_score(case, incidental)["refusal_correct"])

    def test_deterministic_routes_have_structured_provenance_without_citation_marker(self):
        from scripts.eval_case import deterministic_score
        case = {"query": "有哪些主线任务", "should_refuse": False}
        for route in ("enum", "structured"):
            with self.subTest(route=route):
                result = {"route_used": route, "rejected": False,
                          "answer": "知识库中的确定性结果"}
                self.assertTrue(deterministic_score(case, result)["citation_present"])


class StreamTests(unittest.TestCase):
    def test_partial_eof_or_done_without_finish_is_not_success_or_retried(self):
        for tail in ([], ["data: [DONE]"]):
            with self.subTest(tail=tail):
                response = MagicMock()
                response.status_code = 200
                response.iter_lines.return_value = iter([
                    'data: {"choices":[{"delta":{"content":"partial"}}]}', *tail])
                http = MagicMock()
                http.return_value.__enter__.return_value.stream.return_value.__enter__.return_value = response
                client = LLMClient()
                client.api_key = "test-only"
                with patch("scripts.llm_client.httpx.Client", http):
                    stream = client.chat_stream("test")
                    self.assertEqual(next(stream), "partial")
                    with self.assertRaisesRegex(RuntimeError, "结束原因"):
                        next(stream)
                self.assertEqual(http.call_count, 1)

    def test_expired_total_deadline_opens_no_request(self):
        client = LLMClient()
        client.api_key = "test-only"
        client.max_retries = 0
        with patch("scripts.llm_client.httpx.Client") as http:
            with self.assertRaisesRegex(RuntimeError, "总时限"):
                list(client.chat_stream("test", _deadline=time.perf_counter() - 1))
        http.assert_not_called()

    def test_nonstream_continuation_reuses_one_deadline(self):
        client = LLMClient()
        client.api_key = "test-only"
        responses = [
            {"choices": [{"message": {"content": "前"}, "finish_reason": "length"}]},
            {"choices": [{"message": {"content": "后"}, "finish_reason": "stop"}]},
        ]
        with patch.object(client, "_chat_completions", side_effect=responses) as call:
            self.assertEqual(client.chat("test"), "前后")
        deadlines = [item.kwargs["_deadline"] for item in call.call_args_list]
        self.assertEqual(deadlines[0], deadlines[1])


if __name__ == "__main__":
    unittest.main()
