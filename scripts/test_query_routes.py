# -*- coding: utf-8 -*-
"""离线检索编排回归；不加载向量模型、不调用 LLM。"""
import unittest
from unittest.mock import patch, Mock

from scripts import rag_ask


def hit(name, **flags):
    return {"meta": {"name": name, "category": "干员语音", "item_id": name},
            "text": name, "score": 0.5, **flags}


class QueryRouteTests(unittest.TestCase):
    def setUp(self):
        self.mocks = {}
        for name in ("rag_search", "keyword_search", "mention_lookup", "kb_direct_hits"):
            patcher = patch.object(rag_ask, name, return_value=[])
            self.mocks[name] = patcher.start()
            self.addCleanup(patcher.stop)
        self.plan = {"routes": ["entity_direct", "rag", "keyword"],
                     "entities": ["莱万汀"], "keywords": ["吃", "食物"],
                     "search_queries": ["莱万汀 吃 饮食偏好"]}

    def test_unselected_mention_is_not_executed(self):
        rag_ask.multi_search("莱万汀喜欢吃什么", plan=self.plan)
        self.mocks["mention_lookup"].assert_not_called()
        self.assertTrue(self.mocks["rag_search"].called)
        for call in self.mocks["rag_search"].call_args_list:
            self.assertFalse(call.kwargs["direct_fallback"])

    def test_keyword_search_is_scoped_to_each_entity(self):
        self.plan["entities"].append("佩丽卡")
        rag_ask.multi_search("两位喜欢吃什么", plan=self.plan)
        terms = [c.args[0] for c in self.mocks["keyword_search"].call_args_list]
        self.assertEqual(terms, [["莱万汀", "吃"], ["佩丽卡", "吃"],
                                 ["莱万汀", "食物"], ["佩丽卡", "食物"]])

    def test_rag_only_does_not_run_other_routes(self):
        self.plan["routes"] = ["rag"]
        rag_ask.multi_search("莱万汀喜欢吃什么", plan=self.plan)
        for name in ("keyword_search", "mention_lookup", "kb_direct_hits"):
            self.mocks[name].assert_not_called()

    def test_mention_only_does_not_run_rag_or_direct(self):
        self.plan["routes"] = ["mention"]
        rag_ask.multi_search("谁提到了莱万汀", plan=self.plan)
        self.mocks["mention_lookup"].assert_called_once()
        self.mocks["rag_search"].assert_not_called()
        self.mocks["kb_direct_hits"].assert_not_called()

    def test_graph_miss_has_text_fallback(self):
        self.plan["routes"] = ["graph"]
        rag_ask.multi_search("莱万汀", plan=self.plan)
        self.mocks["rag_search"].assert_called()

    def test_keyword_upgrades_existing_hit_and_precedes_mentions(self):
        self.plan["routes"].append("mention")
        self.mocks["rag_search"].return_value = [hit("莱万汀语音")]
        self.mocks["keyword_search"].return_value = [
            {"name": "莱万汀语音", "category": "干员语音", "item_id": "莱万汀语音", "full_text": "吃冰淇淋"}]
        self.mocks["mention_lookup"].return_value = [hit(f"提及{i}", _mention=True) for i in range(3)]
        hits = rag_ask.multi_search("莱万汀喜欢吃什么", plan=self.plan)
        self.assertEqual(hits[0]["text"], "吃冰淇淋")
        self.assertTrue(hits[0]["_keyword"])
        self.assertEqual(len(hits), 4)


class DirectFallbackTests(unittest.TestCase):
    def test_disabled_direct_fallback_is_respected(self):
        retriever = Mock()
        retriever.search.return_value = [hit("语音")]
        with patch.object(rag_ask, "_get_retriever", return_value=retriever), \
                patch.object(rag_ask, "extract_kb_entity", return_value=("莱万汀", {"full_text": "档案"})), \
                patch.object(rag_ask, "kb_direct_hits") as direct:
            hits = rag_ask.rag_search("莱万汀", direct_fallback=False)
        direct.assert_not_called()
        self.assertEqual(hits[0]["meta"]["name"], "语音")


if __name__ == "__main__":
    unittest.main()
