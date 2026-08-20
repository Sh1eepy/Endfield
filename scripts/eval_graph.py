# -*- coding: utf-8 -*-
"""离线 GraphRAG 单跳/多跳路径评测。"""
from __future__ import annotations

import argparse
import json
import os

from graph_search import graph_query

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def evaluate(eval_path="output/eval/graph_eval_set.jsonl"):
    path = eval_path if os.path.isabs(eval_path) else os.path.join(ROOT, eval_path)
    cases = [json.loads(line) for line in open(path, encoding="utf-8") if line.strip()]
    details = []
    passed = 0
    for case in cases:
        result = graph_query(case["query"], top_k=12)
        rendered = "\n".join(x.get("path", "") + "\n" + x.get("evidence", "") for x in result.get("paths") or [])
        missing = [term for term in case["gold_terms"] if term not in rendered]
        ok = bool(result.get("paths")) and not missing
        passed += int(ok)
        details.append({"query": case["query"], "case": case["case"], "passed": ok,
                        "missing_terms": missing, "path_count": len(result.get("paths") or []),
                        "entities": [x["name"] for x in result.get("entities") or []]})
    recall = passed / len(cases) if cases else 0.0
    return {"summary": {"cases": len(cases), "passed": passed, "path_recall": recall}, "details": details}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", default="output/eval/graph_eval_set.jsonl")
    ap.add_argument("--out", default="output/eval/graph_result.json")
    ap.add_argument("--min-recall", type=float, default=0.90)
    args = ap.parse_args()
    result = evaluate(args.eval)
    out = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["summary"]["path_recall"] < args.min_recall:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
