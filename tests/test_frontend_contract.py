# -*- coding: utf-8 -*-
"""前端核心结构与新版视觉契约静态测试。

React 重构后前端源码位于 web/src/（组件 tsx + 分层 css）。本测试扫描全部源码文本，
保证关键 DOM id、视觉 token、动画与交互契约在重构后仍然存在，防止无意回归。
"""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "web" / "src"


def _src_text() -> str:
    parts = []
    for path in sorted(SRC.rglob("*")):
        if path.is_file() and path.suffix in (".tsx", ".ts", ".css"):
            try:
                parts.append(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError):
                continue
    return "\n".join(parts)


HTML = _src_text()


class FrontendContractTests(unittest.TestCase):
    def test_api_bound_elements_remain_available(self):
        for token in ('id="api-dot"', 'id="api-text"', 'id="mode-tabs"', 'id="in-search"',
                      'id="suggest"', 'id="search-history"', 'id="tree-title"', 'id="syn-tree"'):
            self.assertIn(token, HTML)

    def test_visual_system_and_motion_are_present(self):
        self.assertIn("--yellow: #f0cf16", HTML)
        self.assertIn("@keyframes heroRise", HTML)
        self.assertIn("@keyframes contentIn", HTML)
        self.assertIn("prefers-reduced-motion", HTML)

    def test_entry_sequence_is_centered_staged_and_progressive(self):
        for token in ('id="entry-curtain"', 'entry-mechanism', 'mechanicalDock',
                      'entry-beam-a', 'id="entry-percent"', '--boot-progress',
                      'const duration = 3400', "' is-complete'"):
            self.assertIn(token, HTML)

    def test_vertical_image_tree_and_empty_default_are_present(self):
        self.assertIn("X_UNIT", HTML)
        self.assertIn("node-card-image", HTML)
        self.assertIn("EmptyState", HTML)
        self.assertNotIn("$('in-search').value = '重息壤'", HTML)

    def test_search_has_accessible_name(self):
        self.assertIn('aria-label="搜索物品、设备或知识问题"', HTML)

    def test_operator_dossier_supports_tabs_styles_media_and_audio(self):
        for token in ("OperatorDossier", "operator-chapter-nav", "data-op-tab",
                      "tone-rank-yellow", "operator-audio-list", "new Audio(",
                      "operator-scroll-status", "operator-video", "mediaSrc("):
            self.assertIn(token, HTML)

    def test_ask_results_are_cached_by_query(self):
        self.assertIn("askCacheRef", HTML)
        self.assertIn("new Map<", HTML)
        self.assertIn(".get(q)", HTML)
        self.assertIn(".set(q, d)", HTML)

    def test_media_tables_render_as_full_size_galleries(self):
        for token in ("operator-media-grid", "data-media-gallery", "kb-media-img", "mediaTable"):
            self.assertIn(token, HTML)


if __name__ == "__main__":
    unittest.main()
