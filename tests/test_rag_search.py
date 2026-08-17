# -*- coding: utf-8 -*-
"""RAG 名称召回的纯离线单元测试（不加载 embedding 模型）。"""
import unittest

from scripts.rag_search import RAGRetriever


class NameSearchTests(unittest.TestCase):
    def setUp(self):
        self.retriever = RAGRetriever.__new__(RAGRetriever)
        self.retriever.metas = [
            {"name": "游戏定档PV", "category": "游戏视频"},
            {"name": "佩丽卡", "category": "干员"},
            {"name": "【玩家攻略】佩丽卡", "category": "干员攻略"},
            {"name": "【玩家攻略】余烬", "category": "干员攻略"},
            {"name": "能量清淤", "category": "任务"},
        ]

    def names(self, query):
        return [self.retriever.metas[i]["name"] for i, _ in self.retriever.name_search(query, 5)]

    def test_video_core_name_is_recalled(self):
        self.assertEqual(self.names("明日方舟终末地定档PV在哪里看")[0], "游戏定档PV")

    def test_guide_intent_prioritizes_guide_category(self):
        self.assertEqual(self.names("佩丽卡怎么玩")[0], "【玩家攻略】佩丽卡")

    def test_short_task_name_is_recalled(self):
        self.assertIn("能量清淤", self.names("环带来客和清淤哪个强"))


if __name__ == "__main__":
    unittest.main()
