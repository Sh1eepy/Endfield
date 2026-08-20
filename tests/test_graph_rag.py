# -*- coding: utf-8 -*-
import os
import sqlite3
import tempfile
import unittest

from scripts.build_knowledge_graph import create_schema
from scripts.graph_search import GraphRetriever, should_route_graph


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


if __name__ == "__main__":
    unittest.main()
