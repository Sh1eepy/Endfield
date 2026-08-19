# -*- coding: utf-8 -*-
import unittest
from unittest.mock import patch

from scripts.intent_router import classify_batch


class IntentBatchTests(unittest.TestCase):
    def test_batch_handles_rule_and_unclassified_without_llm(self):
        with patch("scripts.intent_router.llm.available", return_value=False):
            result = classify_batch(["重息壤怎么合成", "随便聊聊"])
        self.assertEqual(result["重息壤怎么合成"][0], "配方")
        self.assertEqual(result["重息壤怎么合成"][2], "rule")
        self.assertEqual(result["随便聊聊"][2], "pending")


if __name__ == "__main__":
    unittest.main()
