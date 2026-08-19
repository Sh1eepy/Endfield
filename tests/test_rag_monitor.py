# -*- coding: utf-8 -*-
import unittest

from scripts.rag_monitor import RAGMonitor


class RAGMonitorTests(unittest.TestCase):
    def test_tracks_routes_degradation_and_latency(self):
        monitor = RAGMonitor()
        monitor.observe({"route_used": "rag", "hits": [], "rejected": False}, 120, True)
        monitor.observe({"route_used": "structured"}, 20, True)
        snap = monitor.snapshot()
        self.assertEqual(snap["routes"], {"rag": 1, "structured": 1})
        self.assertEqual(snap["counts"]["empty_retrieval"], 1)
        self.assertEqual(snap["counts"]["llm_degraded"], 1)
        self.assertEqual(snap["latency_ms"]["max"], 120)


if __name__ == "__main__":
    unittest.main()
