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

    def test_entry_sequence_is_centered_staged_and_progressive(self):
        for token in ('id="entry-curtain"', 'entry-mechanism', 'mechanicalDock',
                      'entry-beam-a', 'id="entry-percent"', '--boot-progress',
                      'const duration = 3400', "curtain.classList.add('is-complete')"):
            self.assertIn(token, HTML)

    def test_vertical_image_tree_and_empty_default_are_present(self):
        self.assertIn("nodeSize([116, 148])", HTML)
        self.assertIn("node-card-image", HTML)
        self.assertIn("renderEmptyState('syn')", HTML)
        self.assertNotIn("$('in-search').value = '重息壤'", HTML)

    def test_search_has_accessible_name(self):
        self.assertIn('aria-label="搜索物品、设备或知识问题"', HTML)

    def test_operator_dossier_supports_tabs_styles_media_and_audio(self):
        for token in ("renderOperatorDetail", "operator-chapter-nav", "data-op-tab",
                      "tone-rank-yellow", "operator-audio-list", "new Audio(",
                      "operator-scroll-status", "operator-video", "mediaSrc("):
            self.assertIn(token, HTML)

    def test_ask_results_are_cached_by_query(self):
        self.assertIn("const ASK_CACHE = new Map()", HTML)
        self.assertIn("const cached = ASK_CACHE.get(q)", HTML)
        self.assertIn("ASK_CACHE.set(q, d)", HTML)

    def test_media_tables_render_as_full_size_galleries(self):
        for token in ("operator-media-grid", "data-media-gallery", "kb-media-img", "mediaTable"):
            self.assertIn(token, HTML)


if __name__ == "__main__":
    unittest.main()
