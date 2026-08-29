# -*- coding: utf-8 -*-
"""离线质量门禁：检查索引一致性和已落盘评测指标。"""
import argparse
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as fh:
        return json.load(fh)


def main():
    """汇总评测结果；任一核心指标低于阈值时返回非零状态。"""
    ap = argparse.ArgumentParser()
    ap.add_argument("--min-recall", type=float, default=.98)
    ap.add_argument("--min-mrr", type=float, default=.93)
    ap.add_argument("--min-intent", type=float, default=.85)
    ap.add_argument("--min-route", type=float, default=.90)
    ap.add_argument("--min-refusal", type=float, default=.90)
    ap.add_argument("--min-citation", type=float, default=.90)
    ap.add_argument("--min-source-overlap", type=float, default=.60)
    ap.add_argument("--min-judge-faithfulness", type=float, default=1.50)
    ap.add_argument("--min-graph-recall", type=float, default=.90)
    ap.add_argument("--min-relation-query-pass", type=float, default=.98)
    args = ap.parse_args()
    failures, warnings = [], []
    from build_eval_manifest import build_manifest
    current_manifest = build_manifest()
    stored_manifest = load("output/eval/eval_manifest.json")
    if stored_manifest.get("manifest_id") != current_manifest["manifest_id"]:
        failures.append("eval_manifest_stale")
    status = load("output/rag/build_status.json")
    retrieval_result = load("output/eval/final_reviewed.json")
    retrieval = retrieval_result["summary"]["overall"]
    if (retrieval_result.get("metadata") or {}).get("manifest_id") not in {
            None, current_manifest["manifest_id"]}:
        failures.append("retrieval_manifest_mismatch")
    if "metadata" not in retrieval_result:
        warnings.append("retrieval_result_unversioned")
    if not status.get("consistent"):
        failures.append("index_inconsistent:" + ";".join(status.get("issues", [])))
    if retrieval["recall"] < args.min_recall:
        failures.append(f"recall:{retrieval['recall']}<{args.min_recall}")
    if retrieval["mrr"] < args.min_mrr:
        failures.append(f"mrr:{retrieval['mrr']}<{args.min_mrr}")
    pipeline_path = os.path.join(ROOT, "output/eval/pipeline_result.json")
    if os.path.exists(pipeline_path):
        pipeline_result = load("output/eval/pipeline_result.json")
        p = pipeline_result["summary"]
        if (pipeline_result.get("metadata") or {}).get("manifest_id") not in {
                None, current_manifest["manifest_id"]}:
            failures.append("pipeline_manifest_mismatch")
        if "metadata" not in pipeline_result:
            warnings.append("pipeline_result_unversioned")
        # 正式意图门禁只接受包含 LLM 兜底的完整评测；离线规则报告用于暴露覆盖缺口。
        if p.get("llm_enabled") and p["intent_accuracy"] < args.min_intent:
            failures.append(f"intent_accuracy:{p['intent_accuracy']}<{args.min_intent}")
        if p["route_accuracy"] < args.min_route:
            failures.append(f"route_accuracy:{p['route_accuracy']}<{args.min_route}")
    answer_path = os.path.join(ROOT, "output/eval/answer_result.json")
    if os.path.exists(answer_path):
        answer_result = load("output/eval/answer_result.json")
        a = answer_result["summary"]
        if (answer_result.get("metadata") or {}).get("manifest_id") not in {
                None, current_manifest["manifest_id"]}:
            failures.append("answer_manifest_mismatch")
        if "metadata" not in answer_result:
            warnings.append("answer_result_unversioned")
        for key, threshold in (("refusal_correct", args.min_refusal),
                               ("citation_present", args.min_citation),
                               ("source_overlap", args.min_source_overlap)):
            if a[key] < threshold:
                failures.append(f"{key}:{a[key]}<{threshold}")
        faithfulness = (a.get("judge") or {}).get("faithfulness")
        if faithfulness is not None and faithfulness < args.min_judge_faithfulness:
            failures.append(f"judge_faithfulness:{faithfulness}<{args.min_judge_faithfulness}")
    graph_db_path = os.path.join(ROOT, "output/knowledge_graph/graph.db")
    if os.path.exists(graph_db_path):
        from graph_audit import audit_graph
        from eval_graph import evaluate as evaluate_graph
        graph_audit = audit_graph(graph_db_path)
        if not graph_audit.get("consistent"):
            failures.append("graph_inconsistent:" + ";".join(graph_audit.get("issues") or []))
        graph_recall = evaluate_graph()["summary"]["path_recall"]
        if graph_recall < args.min_graph_recall:
            failures.append(f"graph_path_recall:{graph_recall}<{args.min_graph_recall}")
        from audit_relation_queries import audit_relation_queries
        relation_pass = audit_relation_queries(graph_db_path, sample_per_predicate=20)["pass_rate"]
        if relation_pass < args.min_relation_query_pass:
            failures.append(f"relation_query_pass:{relation_pass}<{args.min_relation_query_pass}")
    print(json.dumps({"passed": not failures, "failures": failures, "warnings": warnings},
                     ensure_ascii=False, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
