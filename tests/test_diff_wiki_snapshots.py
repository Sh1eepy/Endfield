import json
import os
import tempfile
import unittest

from scripts.diff_wiki_snapshots import compare


def snapshot(entries):
    return {
        "meta": {"total_catalog_entries": len(entries), "detail_success": len(entries),
                 "detail_failed": 0},
        "catalog": entries,
    }


def entry(item_id, name, text="正文", category="物品"):
    return {"subTypeName": category, "mainTypeName": "百科",
            "item": {"itemId": item_id, "name": name},
            "detail": {"item": {"name": name, "text": text}}}


class SnapshotDiffTests(unittest.TestCase):
    def test_reports_added_deleted_changed_and_validates_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_path, new_path = os.path.join(tmp, "old.json"), os.path.join(tmp, "new.json")
            with open(old_path, "w", encoding="utf-8") as fh:
                json.dump(snapshot([entry("1", "甲"), entry("2", "乙")]), fh)
            with open(new_path, "w", encoding="utf-8") as fh:
                json.dump(snapshot([entry("1", "甲", "新正文"), entry("3", "丙")]), fh)
            result = compare(old_path, new_path)
        self.assertEqual([x["item_id"] for x in result["delta"]["added"]], ["3"])
        self.assertEqual([x["item_id"] for x in result["delta"]["deleted"]], ["2"])
        self.assertEqual([x["item_id"] for x in result["delta"]["changed"]], ["1"])
        self.assertEqual(result["new"]["validation_errors"], [])


if __name__ == "__main__":
    unittest.main()
