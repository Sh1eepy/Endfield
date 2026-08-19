# -*- coding: utf-8 -*-
"""干员详情结构库完整性测试。"""
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OperatorDetailsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((ROOT / "output" / "operator_details.json").read_text(encoding="utf-8"))

    def test_every_operator_has_identity_and_chapters(self):
        operators = self.data["operators"]
        self.assertEqual(self.data["meta"]["count"], len(operators))
        self.assertGreaterEqual(len(operators), 30)
        for item_id, operator in operators.items():
            with self.subTest(item_id=item_id):
                self.assertEqual(operator["item_id"], item_id)
                self.assertTrue(operator["name"])
                self.assertTrue(operator["chapters"])

    def test_dataset_preserves_rich_styles_images_and_audio(self):
        raw = json.dumps(self.data, ensure_ascii=False)
        self.assertIn('"color": "light_rank_yellow"', raw)
        self.assertIn('"t": "img"', raw)
        self.assertIn('"t": "video"', raw)
        self.assertIn('"img": "https://bbs.hycdn.cn/image/', raw)
        self.assertIn('"url": "https://bbs.hycdn.cn/audio/', raw)


if __name__ == "__main__":
    unittest.main()
