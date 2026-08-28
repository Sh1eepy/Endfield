# -*- coding: utf-8 -*-
"""RAG 增量索引自愈测试。"""
import os
import json
import pickle
import tempfile
import unittest

from scripts.build_rag import inconsistent_bm25_categories, load_operator_audio_records, split_chunks


class Bm25ConsistencyTests(unittest.TestCase):
    def test_long_record_without_sections_falls_back_to_full_text(self):
        record = {"full_text": "第一段内容\n" + "第二段内容" * 20, "sections": {}}
        chunks = split_chunks(record, 40)
        self.assertGreater(len(chunks), 0)
        self.assertIn("第一段内容", chunks[0])

    def test_long_record_keeps_full_text_not_covered_by_sections(self):
        record = {
            "full_text": "名称：莱万汀\n基础资料：已收录正文\n其他内容：她非常喜欢吃冰淇淋。",
            "sections": {"基础资料": "已收录正文"},
        }
        chunks = split_chunks(record, 20)
        self.assertTrue(any("冰淇淋" in chunk for chunk in chunks))
        self.assertTrue(all(len(chunk) <= 20 for chunk in chunks))

    def test_loads_only_chinese_operator_voice_transcripts(self):
        payload = {"operators": {"42": {"name": "测试干员", "chapters": [
            {"title": "语音记录", "widgets": [{"title": "干员语音", "tabs": [
                {"title": "中文：测试CV", "audios": [
                    {"id": "cn1", "title": "闲聊", "profile": "我喜欢冰淇淋。", "url": "cn.wav"}]},
                {"title": "英语：Test", "audios": [
                    {"id": "en1", "title": "Chat", "profile": "I like ice cream.", "url": "en.wav"}]},
            ]}]},
            {"title": "官方情报", "widgets": [{"title": "EP", "tabs": [
                {"title": "default", "audios": [
                    {"id": "ep1", "title": "EP", "profile": "演职员信息", "url": "ep.mp3"}]},
            ]}]},
        ]}}}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "operator_details.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)
            records = load_operator_audio_records(path)
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["source_kind"], "operator_audio")
        self.assertIn("冰淇淋", records[0]["full_text"])
        self.assertNotIn("I like", records[0]["full_text"])

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
