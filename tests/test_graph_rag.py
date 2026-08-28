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

    def test_large_enum_prompt_discloses_total_and_truncation(self):
        names = [f"任务{i}" for i in range(55)]
        enum = {"names": names, "label": "主线任务", "category": "任务"}
        with patch.object(rag_ask, "classify_query", return_value=("知识", 1.0, "rule")), \
                patch.object(rag_ask, "enum_lookup", return_value=enum), \
                patch.object(rag_ask.llm, "available", return_value=True), \
                patch.object(rag_ask.llm, "chat", return_value="整理结果") as chat:
            result = rag_ask.ask("主线任务有哪些", gen_answer_=True)
        prompt = chat.call_args.args[0]
        self.assertEqual(result["count"], 55)
        self.assertIn("总数：55", prompt)
        self.assertIn("前 40 项", prompt)
        self.assertIn("不得把当前清单说成完整清单", prompt)

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
