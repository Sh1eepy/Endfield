# -*- coding: utf-8 -*-
"""知识图谱一致性、来源追溯与关系约束审计。"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
from datetime import datetime, timezone

from build_knowledge_graph import DEFAULT_DB, content_hash, load_rows

ALLOWED_PREDICATES = {
    "REFERENCES", "HAS_PARTICIPANT", "LOCATED_IN", "PREVIOUS_QUEST", "NEXT_QUEST",
    "AFFILIATED_WITH", "PART_OF", "REWARDS", "UNLOCKS", "RECOMMENDS_WEAPON",
    "REQUIRES_MATERIAL", "OBTAINED_FROM", "USED_FOR", "RECOMMENDED_FOR",
    "DEVICE_USES_INPUT", "DEVICE_PRODUCES", "AUTHORITY",
}


def audit_graph(db_path=DEFAULT_DB):
    issues = []
    if not os.path.exists(db_path):
        return {"status": "fail", "consistent": False, "issues": ["graph_db_missing"]}
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    required = {"meta", "entities", "aliases", "relations", "manifest"}
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not required <= tables:
        return {"status": "fail", "consistent": False,
                "issues": ["missing_tables:" + ",".join(sorted(required - tables))]}
    fk = list(con.execute("PRAGMA foreign_key_check"))
    if fk:
        issues.append(f"foreign_key_errors:{len(fk)}")
    predicates = {r[0] for r in con.execute("SELECT DISTINCT predicate FROM relations")}
    unknown = predicates - ALLOWED_PREDICATES
    if unknown:
        issues.append("unknown_predicates:" + ",".join(sorted(unknown)))
    empty_evidence = con.execute("SELECT COUNT(*) FROM relations WHERE trim(evidence)='' ").fetchone()[0]
    if empty_evidence:
        issues.append(f"relations_without_evidence:{empty_evidence}")
    bad_status = con.execute("SELECT COUNT(*) FROM relations WHERE review_status NOT IN ('verified','human_verified')").fetchone()[0]
    if bad_status:
        issues.append(f"unreviewed_relations:{bad_status}")
    self_loops = con.execute("SELECT COUNT(*) FROM relations WHERE subject_id=object_id").fetchone()[0]
    if self_loops:
        issues.append(f"self_loops:{self_loops}")
    dangling_sources = con.execute("""SELECT COUNT(*) FROM relations r LEFT JOIN manifest m
                                      ON m.source_item_id=r.source_item_id
                                      WHERE m.source_item_id IS NULL AND r.extraction_method!='recipe_rule'""").fetchone()[0]
    if dangling_sources:
        issues.append(f"relations_with_missing_source:{dangling_sources}")
    rows = load_rows()
    expected = {str(r.get("item_id") or ""): content_hash(r) for r in rows}
    actual = {r["source_item_id"]: r["content_hash"] for r in con.execute("SELECT source_item_id,content_hash FROM manifest")}
    missing = set(expected) - set(actual)
    stale = [k for k, value in expected.items() if actual.get(k) != value]
    extra = set(actual) - set(expected)
    if missing or extra:
        issues.append(f"manifest_key_mismatch:missing={len(missing)},extra={len(extra)}")
    if stale:
        issues.append(f"stale_sources:{len(stale)}")
    counts = {
        "entities": con.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
        "aliases": con.execute("SELECT COUNT(*) FROM aliases").fetchone()[0],
        "relations": con.execute("SELECT COUNT(*) FROM relations").fetchone()[0],
        "sources": con.execute("SELECT COUNT(*) FROM manifest").fetchone()[0],
        "predicates": {r[0]: r[1] for r in con.execute("SELECT predicate,COUNT(*) FROM relations GROUP BY predicate")},
    }
    con.close()
    return {"status": "ok" if not issues else "degraded", "consistent": not issues,
            "checked_at": datetime.now(timezone.utc).isoformat(), "issues": issues, **counts}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="output/knowledge_graph/graph.db")
    ap.add_argument("--out", default="output/knowledge_graph/audit_report.json")
    ap.add_argument("--fail-on-error", action="store_true")
    args = ap.parse_args()
    db = args.db if os.path.isabs(args.db) else os.path.join(os.path.dirname(os.path.dirname(__file__)), args.db)
    result = audit_graph(db)
    out = args.out if os.path.isabs(args.out) else os.path.join(os.path.dirname(os.path.dirname(__file__)), args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.fail_on_error and not result["consistent"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
