"""Offline regressions for entity, stream termination and incremental index fixes."""
import os
import sqlite3
import unittest
from unittest.mock import MagicMock, patch

os.environ["LLM_API_KEY"] = ""
os.environ["HF_HUB_OFFLINE"] = "1"
from scripts import rag_ask
from scripts import api_server
from scripts.build_knowledge_graph import (GraphBuilder, content_hash as graph_content_hash,
                                           create_schema)
from scripts.build_rag import diff_chunks
from scripts.llm_client import LLMClient


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


if __name__ == "__main__":
    unittest.main()
