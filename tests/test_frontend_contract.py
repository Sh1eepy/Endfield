# -*- coding: utf-8 -*-
"""前端核心结构与新版视觉契约静态测试。"""
from pathlib import Path
import unittest


HTML = (Path(__file__).resolve().parents[1] / "web" / "index.html").read_text(encoding="utf-8")


class FrontendContractTests(unittest.TestCase):
    def test_api_bound_elements_remain_available(self):
        for element_id in ("api-dot", "api-text", "mode-tabs", "in-search", "suggest", "search-history", "tree-title", "syn-tree"):
            self.assertIn(f'id="{element_id}"', HTML)

    def test_new_visual_system_and_motion_are_present(self):
        self.assertIn("--yellow:#f2d321", HTML)
        self.assertIn("@keyframes heroRise", HTML)
        self.assertIn("@keyframes contentIn", HTML)
        self.assertIn("prefers-reduced-motion", HTML)

    def test_vertical_image_tree_and_empty_default_are_present(self):
        self.assertIn("nodeSize([116, 148])", HTML)
        self.assertIn("node-card-image", HTML)
        self.assertIn("renderEmptyState('syn')", HTML)
        self.assertNotIn("$('in-search').value = '重息壤'", HTML)

    def test_search_has_accessible_name(self):
        self.assertIn('aria-label="搜索物品、设备或知识问题"', HTML)

    def test_operator_dossier_supports_tabs_styles_media_and_audio(self):
        for token in ("renderOperatorDetail", "operator-chapter-nav", "data-op-tab",
                      "tone-rank-yellow", "operator-audio-list", "new Audio("):
            self.assertIn(token, HTML)


if __name__ == "__main__":
    unittest.main()
