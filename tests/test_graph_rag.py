# -*- coding: utf-8 -*-
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from scripts.build_knowledge_graph import create_schema
from scripts.graph_search import GraphRetriever, should_route_graph
from scripts import rag_ask
from scripts.rag_ask import focus_long_context, is_interpretive_relation, relationship_evidence_hits, semantic_plan


class GraphRAGTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "graph.db")
        con = sqlite3.connect(self.db)
        create_schema(con, reset=True)
        con.executemany("INSERT INTO entities(id,canonical_name,entity_type) VALUES(?,?,?)", [
            ("p1", "甲", "person"), ("p2", "乙", "person"), ("q1", "共同任务", "quest"),
            ("o1", "测试组织", "organization")])
        con.executemany("""INSERT INTO relations
          (id,subject_id,predicate,object_id,source_item_id,evidence,confidence,extraction_method,review_status)
          VALUES(?,?,?,?,?,?,?,?,?)""", [
            ("r1", "q1", "HAS_PARTICIPANT", "p1", "s1", "相关人物：甲", 1, "rule", "verified"),
            ("r2", "q1", "HAS_PARTICIPANT", "p2", "s1", "相关人物：乙", 1, "rule", "verified"),
            ("r3", "p1", "AFFILIATED_WITH", "o1", "s1", "身份认证：测试组织", 1, "rule", "verified")])
        con.execute("INSERT INTO aliases VALUES(?,?,?,?,?,?,?)",
                    ("甲本名", "p1", "real_name", "s1", "人工审定", 1, "human_verified"))
        con.commit(); con.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_two_hop_common_task(self):
        retriever = GraphRetriever(self.db)
        result = retriever.search("甲和乙的关系")
        self.assertTrue(result["paths"])
        self.assertEqual(result["paths"][0]["hops"], 2)
        retriever.con.close()

    def test_affiliation_and_alias(self):
        retriever = GraphRetriever(self.db)
        self.assertIn("测试组织", retriever.search("甲属于哪个组织")["paths"][0]["path"])
        self.assertIn("甲本名", retriever.search("甲的本名")["paths"][0]["path"])
        retriever.con.close()

    def test_relation_router_is_narrow(self):
        self.assertTrue(should_route_graph("甲和乙是什么关系"))
        self.assertFalse(should_route_graph("介绍一下甲的故事"))

    def test_reverse_and_boolean_relation_queries(self):
        retriever = GraphRetriever(self.db)
        self.assertIn("测试组织", retriever.search("测试组织和甲是什么关系", max_hops=1)["paths"][0]["path"])
        self.assertTrue(retriever.search("甲是不是与测试组织有关系", max_hops=1)["paths"])
        retriever.con.close()

    def test_interpretive_relation_is_separate_route(self):
        self.assertTrue(is_interpretive_relation("诀是不是挺中意管理员"))
        self.assertTrue(is_interpretive_relation("狼卫的妹妹是不是很可爱"))
        self.assertFalse(is_interpretive_relation("诀属于哪个组织"))
        self.assertFalse(is_interpretive_relation("莱万汀喜欢吃什么"))

    def test_relationship_evidence_requires_subject_and_target(self):
        kb = {"测试人物": {"category": "干员", "full_text": ""},
              "管理员": {"category": "干员", "full_text": ""}}
        entries = [
            {"name": "测试人物", "category": "干员", "item_id": "1",
             "full_text": "记录：她对管理员十分信任，并毫不犹豫地签下合作协议。"},
            {"name": "无关人物语音", "category": "语音", "item_id": "2",
             "full_text": "管理员，今天也辛苦了。"},
        ]
        with patch.object(rag_ask, "_get_kb_names", return_value=kb), \
                patch.object(rag_ask, "_load_all_kb_entries", return_value=entries):
            hits = relationship_evidence_hits("测试人物对管理员的态度")
        self.assertTrue(hits)
        self.assertTrue(all(h["meta"]["name"] == "测试人物" for h in hits))
        self.assertTrue(all("管理员" in h["text"] for h in hits))

    def test_semantic_planner_distinguishes_preference_from_relation(self):
        planned = {"question_type": "preference", "topic": "饮食偏好",
                   "entities": ["莱万汀"], "keywords": ["食物", "饮食", "喜欢"],
                   "search_queries": ["莱万汀 饮食偏好"],
                   "routes": ["entity_direct", "rag", "keyword"], "needs_graph": False}
        with patch.object(rag_ask.llm, "available", return_value=True), \
                patch.object(rag_ask.llm, "chat_json", return_value=planned):
            result = semantic_plan("莱万汀喜欢吃什么")
        self.assertEqual(result["question_type"], "preference")
        self.assertNotIn("relationship_evidence", result["routes"])
        self.assertEqual(result["planner_method"], "llm")

    def test_preference_plan_uses_rag_instead_of_relationship_route(self):
        plan = {"question_type": "preference", "topic": "饮食偏好", "entities": ["莱万汀"],
                "keywords": ["食物"], "search_queries": ["莱万汀 饮食偏好"],
                "routes": ["entity_direct", "rag", "keyword"], "needs_graph": False,
                "planner_method": "llm"}
        # 即使宽规则误判为配方，只要结构化直查未命中，语义规划也应纠正为对象偏好。
        with patch.object(rag_ask, "classify_query", return_value=("配方", 1.0, "rule")), \
                patch.object(rag_ask, "enum_lookup", return_value=None), \
                patch.object(rag_ask, "extract_item_name", return_value=(None, None)), \
                patch.object(rag_ask, "recipe_lookup", return_value=None), \
                patch.object(rag_ask, "semantic_plan", return_value=plan), \
                patch.object(rag_ask, "relationship_evidence_hits") as relation_hits, \
                patch.object(rag_ask, "multi_search", return_value=[]) as search:
            result = rag_ask.ask("莱万汀喜欢吃什么")
        relation_hits.assert_not_called()
        search.assert_called_once_with("莱万汀喜欢吃什么", top_k=5, plan=plan)
        self.assertEqual(result["route_used"], "rag")
        self.assertEqual(result["intent"], "偏好")

    def test_long_context_finds_evidence_beyond_prefix(self):
        text = ("无关的档案开头。" * 300) + "\n关键记录：测试角色的妹妹叫远端答案。\n" + ("无关结尾。" * 80)
        focused = focus_long_context(text, "测试角色的妹妹叫什么", max_chars=500)
        self.assertIn("远端答案", focused)
        self.assertLessEqual(len(focused), 520)

    def test_large_enum_returns_every_name_without_llm_truncation(self):
        names = [f"任务{i}" for i in range(55)]
        enum = {"names": names, "label": "主线任务", "category": "任务"}
        with patch.object(rag_ask, "classify_query", return_value=("知识", 1.0, "rule")), \
                patch.object(rag_ask, "enum_lookup", return_value=enum), \
                patch.object(rag_ask.llm, "chat") as chat:
            result = rag_ask.ask("主线任务有哪些", gen_answer_=True)
        self.assertEqual(result["count"], 55)
        self.assertEqual(result["names"], names)
        self.assertIn("共找到 55 个主线任务", result["answer"])
        self.assertIn("55. 任务54", result["answer"])
        chat.assert_not_called()

    def test_enum_lookup_default_keeps_all_matches(self):
        entries = [
            {"name": f"第一章 - 进程 - 任务{i}", "category": "任务", "item_id": str(i),
             "full_text": ""}
            for i in range(55)
        ]
        with patch.object(rag_ask, "_load_all_kb_entries", return_value=entries):
            result = rag_ask.enum_lookup("列出所有主线任务")
        self.assertEqual(len(result["names"]), 55)

    def test_generation_helper_preserves_or_merges_route_result(self):
        base = {"ok": True, "route_used": "rag"}
        with patch.object(rag_ask, "gen_answer") as generate:
            self.assertIs(rag_ask.attach_generated_answer(base, "问题", [], 5, False), base)
            generate.assert_not_called()
        with patch.object(rag_ask, "gen_answer", return_value={"answer": "回答", "rejected": False}):
            result = rag_ask.attach_generated_answer(base.copy(), "问题", [], 5, True)
        self.assertEqual(result["answer"], "回答")


if __name__ == "__main__":
    unittest.main()
