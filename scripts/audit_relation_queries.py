# -*- coding: utf-8 -*-
"""自动生成并审查关系的正问、反问、是非问，防止只修单个用户样例。"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone

from build_knowledge_graph import DEFAULT_DB
from graph_search import GraphRetriever, PREDICATE_LABELS

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUERY_WORD = {
    "AFFILIATED_WITH": "所属组织", "HAS_PARTICIPANT": "相关人物", "LOCATED_IN": "地点",
    "PREVIOUS_QUEST": "前置任务", "NEXT_QUEST": "后续任务", "PART_OF": "属于哪里",
    "REWARDS": "奖励", "UNLOCKS": "解锁什么", "RECOMMENDS_WEAPON": "推荐武器",
    "REQUIRES_MATERIAL": "需要什么材料", "OBTAINED_FROM": "来源", "USED_FOR": "有什么用",
    "RECOMMENDED_FOR": "适合谁", "DEVICE_USES_INPUT": "需要什么原料",
    "DEVICE_PRODUCES": "生产什么", "AUTHORITY": "领袖是谁",
    "YOUNGER_SISTER_OF": "妹妹是谁", "OLDER_BROTHER_OF": "哥哥是谁",
}


def audit_relation_queries(db_path=DEFAULT_DB, sample_per_predicate=40):
    """为每类关系批量验证正向、反向和是非问是否能找回原边。"""
    con = sqlite3.connect(db_path); con.row_factory = sqlite3.Row
    rows = [dict(r) for r in con.execute("""SELECT r.predicate,s.canonical_name subject,o.canonical_name object_name
      FROM relations r JOIN entities s ON s.id=r.subject_id JOIN entities o ON o.id=r.object_id
      WHERE r.predicate!='REFERENCES' ORDER BY r.predicate,r.id""")]
    con.close()
    grouped = defaultdict(list)
    for row in rows:
        if len(row["subject"]) >= 2 and len(row["object_name"]) >= 2:
            grouped[row["predicate"]].append(row)
    retriever = GraphRetriever(db_path)
    failures, counts = [], defaultdict(lambda: {"tested": 0, "passed": 0})
    try:
        for predicate, relations in grouped.items():
            word = QUERY_WORD.get(predicate, PREDICATE_LABELS.get(predicate, predicate))
            for row in relations[:sample_per_predicate]:
                tests = [
                    ("forward", f"{row['subject']}的{word}是什么", row["object_name"]),
                    ("reverse", f"{row['object_name']}和{row['subject']}是什么关系", row["subject"]),
                    ("boolean", f"{row['subject']}是不是与{row['object_name']}有关系", row["object_name"]),
                ]
                for direction, query, expected in tests:
                    result = retriever.search(query, max_hops=1, top_k=20)
                    rendered = "\n".join(p.get("path", "") for p in result["paths"])
                    ok = expected in rendered and row["subject"] in rendered and row["object_name"] in rendered
                    key = f"{predicate}:{direction}"; counts[key]["tested"] += 1
                    counts[key]["passed"] += int(ok)
                    if not ok:
                        failures.append({"predicate": predicate, "direction": direction,
                                         "query": query, "expected": expected})
    finally:
        retriever.con.close()
    tested = sum(x["tested"] for x in counts.values()); passed = sum(x["passed"] for x in counts.values())
    return {"checked_at": datetime.now(timezone.utc).isoformat(), "tested": tested, "passed": passed,
            "pass_rate": passed / tested if tested else 0.0, "by_family": dict(counts),
            "failures": failures[:200], "consistent": tested > 0 and passed == tested}


def main():
    """运行关系问法审查并落盘结果，供质量门禁读取。"""
    ap = argparse.ArgumentParser(); ap.add_argument("--db", default="output/knowledge_graph/graph.db")
    ap.add_argument("--out", default="output/knowledge_graph/relation_query_audit.json")
    ap.add_argument("--sample-per-predicate", type=int, default=40); ap.add_argument("--fail-on-error", action="store_true")
    args = ap.parse_args(); db = args.db if os.path.isabs(args.db) else os.path.join(ROOT, args.db)
    result = audit_relation_queries(db, args.sample_per_predicate)
    out = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh: json.dump(result, fh, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.fail_on_error and not result["consistent"]: raise SystemExit(1)


if __name__ == "__main__": main()
