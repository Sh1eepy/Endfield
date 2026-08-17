# -*- coding: utf-8 -*-
"""RAG 增量索引自愈测试。"""
import os
import pickle
import tempfile
import unittest

from scripts.build_rag import inconsistent_bm25_categories, split_chunks


class Bm25ConsistencyTests(unittest.TestCase):
    def test_long_record_without_sections_falls_back_to_full_text(self):
        record = {"full_text": "第一段内容\n" + "第二段内容" * 20, "sections": {}}
        chunks = split_chunks(record, 40)
        self.assertGreater(len(chunks), 0)
        self.assertIn("第一段内容", chunks[0])

    def test_detects_stale_missing_and_obsolete_shards(self):
        chunks = [
            {"meta": {"category": "干员", "item_id": "1", "chunk_index": 0}},
            {"meta": {"category": "攻略", "item_id": "2", "chunk_index": 0}},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "干员.pkl"), "wb") as f:
                pickle.dump({"metas": [{"item_id": "old", "chunk_index": 0}]}, f)
            with open(os.path.join(tmp, "废弃.pkl"), "wb") as f:
                pickle.dump({"metas": []}, f)
            self.assertEqual(
                inconsistent_bm25_categories(chunks, tmp),
                {"干员", "攻略", "废弃"},
            )


if __name__ == "__main__":
    unittest.main()
