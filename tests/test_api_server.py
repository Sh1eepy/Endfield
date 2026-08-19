# -*- coding: utf-8 -*-
"""核心 API 与合成树离线回归测试。"""
import os
import unittest
from unittest.mock import patch

os.environ.setdefault("HF_HUB_OFFLINE", "1")

from scripts import api_server


def _recipe(machine, inputs, outputs, machine_id="m"):
    return {
        "machine": machine,
        "machine_id": machine_id,
        "duration": 1,
        "inputs": [
            {"item_id": iid, "name": name, "count": count}
            for iid, name, count in inputs
        ],
        "outputs": [
            {"item_id": iid, "name": name, "count": count}
            for iid, name, count in outputs
        ],
    }


class SynthesisTreeTests(unittest.TestCase):
    def test_tree_reaches_base_resources(self):
        recipes = [
            _recipe("加工机", [("ore", "矿石", 2)], [("part", "零件", 1)]),
            _recipe("装配机", [("part", "零件", 3), ("water", "清水", 1)], [("target", "成品", 1)]),
        ]
        index = api_server.build_item_index(recipes)
        tree, error = api_server.build_synthesis_tree("target", recipes, index)

        self.assertIsNone(error)
        self.assertEqual(tree["name"], "成品")
        leaves = []

        def walk(node):
            if node.get("leaf"):
                leaves.append(node["name"])
            for recipe in node.get("recipes", []):
                for child in recipe["inputs"]:
                    walk(child)

        walk(tree)
        self.assertCountEqual(leaves, ["矿石", "清水"])

    def test_cycle_recipe_is_pruned(self):
        recipes = [
            _recipe("循环机", [("b", "材料B", 1)], [("a", "材料A", 1)]),
            _recipe("循环机", [("a", "材料A", 1)], [("b", "材料B", 1)]),
        ]
        index = api_server.build_item_index(recipes)
        tree, _ = api_server.build_synthesis_tree("a", recipes, index)
        self.assertIsNone(tree)

    def test_self_loop_recipe_is_excluded(self):
        recipes = [
            _recipe("错误机", [("a", "材料A", 1)], [("a", "材料A", 2)]),
            _recipe("正确机", [("ore", "矿石", 1)], [("a", "材料A", 1)]),
        ]
        index = api_server.build_item_index(recipes)
        chosen = api_server._pick_producers(index["a"]["produce_by"], index)
        self.assertEqual([r["machine"] for r in chosen], ["正确机"])


class ApiSmokeTests(unittest.TestCase):
    def setUp(self):
        api_server._NAMES_CACHE = None

    def test_health(self):
        self.assertEqual(api_server.health()["status"], "ok")

    def test_deep_health_reports_index_and_llm_without_network(self):
        result = api_server.health_deep()
        self.assertIn(result["status"], {"ok", "degraded"})
        self.assertGreater(result["manifest_chunks"], 0)
        self.assertIn("key_configured", result["llm"])

    def test_metrics_count_ask_requests(self):
        from rag_monitor import monitor
        before = monitor.snapshot()["counts"].get("requests", 0)
        with patch("rag_ask.ask", return_value={"ok": True, "route_used": "rag", "hits": []}):
            api_server.ask_endpoint(api_server.AskRequest(query="测试", gen_answer=True))
        snap = monitor.snapshot()
        self.assertEqual(snap["counts"]["requests"], before + 1)
        self.assertGreaterEqual(snap["counts"]["empty_retrieval"], 1)

    def test_blank_query_is_rejected(self):
        result = api_server.synthesis("   ")
        self.assertFalse(result["ok"])
        self.assertIn("请输入", result["error"])

    def test_negative_depth_is_rejected(self):
        result = api_server.synthesis("重息壤", max_depth=-1)
        self.assertFalse(result["ok"])
        self.assertIn("max_depth", result["error"])

    def test_real_item_returns_recipe_tree(self):
        result = api_server.synthesis("重息壤")
        self.assertTrue(result["ok"])
        self.assertEqual(result["item"], "重息壤")
        self.assertTrue(result["tree"].get("recipes"))
        self.assertTrue(
            any(recipe.get("cover") for recipe in result["tree"]["recipes"]),
            "真实设备节点应带封面图",
        )

    def test_ambiguous_name_returns_candidates(self):
        result = api_server.synthesis("灼铜")
        self.assertTrue(result["ok"])
        self.assertTrue(result["ambiguous"])
        self.assertGreater(len(result["candidates"]), 1)

    def test_device_returns_recipe_cards(self):
        result = api_server.synthesis("天有洪炉")
        self.assertTrue(result["ok"])
        self.assertEqual(result["tree"]["kind"], "device")
        self.assertTrue(result["tree"]["recipes"])

    def test_kb_fallback(self):
        result = api_server.synthesis("诀")
        self.assertTrue(result["ok"])
        self.assertTrue(result["no_recipe"])
        self.assertEqual(result["kb"]["name"], "诀")

    def test_names_are_sorted_unique_and_cached(self):
        first = api_server.names()
        second = api_server.names()
        self.assertEqual(first["count"], len(first["names"]))
        self.assertEqual(first["names"], sorted(set(first["names"])))
        self.assertIs(first["names"], second["names"])
        self.assertIn("重息壤", first["names"])

    def test_all_real_tree_leaves_obey_base_rule(self):
        recipes = api_server.load_recipes(os.path.join(api_server.ROOT, "output", "recipes.json"))
        index = api_server.build_item_index(recipes)
        produced_ids = {x["item_id"] for recipe in recipes for x in recipe["outputs"]}
        built = 0

        def check(node):
            self.assertLessEqual(node["depth"], 10)
            if node.get("leaf"):
                self.assertTrue(api_server._is_base(node["item_id"], index), node["name"])
            for recipe in node.get("recipes", []):
                self.assertLessEqual(len(node["recipes"]), 2)
                for child in recipe["inputs"]:
                    check(child)

        for item_id in produced_ids:
            tree, _ = api_server.build_synthesis_tree(item_id, recipes, index)
            if tree is not None:
                built += 1
                check(tree)
        self.assertGreater(built, 100)

    def test_ask_endpoint_delegates_without_network(self):
        expected = {"ok": True, "answer": "测试回答"}
        with patch("rag_ask.ask", return_value=expected) as mocked:
            result = api_server.ask_endpoint(
                api_server.AskRequest(query="重息壤是什么", top_k=3, gen_answer=False)
            )
        self.assertEqual(result, expected)
        mocked.assert_called_once_with("重息壤是什么", top_k=3, gen_answer_=False)


if __name__ == "__main__":
    unittest.main()
