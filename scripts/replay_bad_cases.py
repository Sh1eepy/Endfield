"""回放已人工批准的坏例，生成不可覆盖的候选运行和建议归因报告。"""
import argparse
import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from llm_client import observe_llm  # noqa: E402
from rag_ask import ask, rag_search  # noqa: E402
from scripts.rag_trace import RAGTrace, trace_store  # noqa: E402
from build_eval_manifest import evaluation_metadata  # noqa: E402
from scripts.eval_case import (EvaluationCase, deterministic_score, normalized_source,
                               source_name_matches)  # noqa: E402


def sources_in_kb(expected):
    wanted = {normalized_source(x) for x in expected}
    found = set()
    for path in glob.glob(str(ROOT / "endfield_kb" / "*.jsonl")):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    name = normalized_source(json.loads(line).get("name"))
                except (ValueError, TypeError):
                    continue
                if name in wanted:
                    found.add(name)
    return found


def sources_in_index(expected):
    wanted = {normalized_source(x) for x in expected}
    with open(ROOT / "output" / "rag" / "chunks.json", encoding="utf-8") as fh:
        rows = json.load(fh)
    return {normalized_source(x.get("meta", {}).get("name")) for x in rows
            if normalized_source(x.get("meta", {}).get("name")) in wanted}


def source_matches(hit, expected):
    name = normalized_source((hit.get("meta") or {}).get("name") or hit.get("name"))
    return source_name_matches(name, expected)


def layer(status, code, **details):
    return {"status": status, "code": code, **details}


def analyze_retrieval(case, result, trace):
    """只判断文本来源是否进入生产上下文；结构化/图路线在 pipeline 层判断。"""
    if case.expected_route in {"structured", "enum", "graph"}:
        return layer("skipped", "NOT_TEXT_RETRIEVAL_ROUTE")
    expected = case.acceptable_sources
    if not expected:
        return layer("skipped", "NO_SOURCE_GOLD")
    raw, indexed = sources_in_kb(expected), sources_in_index(expected)
    if not raw:
        return layer("failed", "SOURCE_ABSENT_OR_EXTRACTION_MISSING")
    if not indexed:
        return layer("failed", "INDEX_MISSING")
    if any(source_matches(hit, expected) for hit in (result.get("hits") or [])):
        return layer("passed", "SOURCE_IN_CONTEXT")
    pre_fusion = [hit for event in trace.retrieval if event["channel"] != "rrf"
                  for hit in event["hits"]]
    if any(source_matches(hit, expected) for hit in pre_fusion):
        return layer("failed", "FUSION_DROP")
    return layer("failed", "RECALL_MISS")


def analyze_pipeline(case, result):
    """检索通过后才判断生产路由；图缺失优先于普通 route mismatch。"""
    if not case.expected_route:
        return layer("failed", "GOLD_ROUTE_MISSING")
    if case.expected_route == "graph" and not (result.get("graph") or {}).get("paths"):
        return layer("failed", "GRAPH_MISSING")
    if result.get("route_used") != case.expected_route:
        return layer("failed", "ROUTE_WRONG", expected=case.expected_route,
                     actual=result.get("route_used"))
    return layer("passed", "ROUTE_CORRECT")


def analyze_answer(case, result):
    scores = deterministic_score(case, result)
    if not scores["refusal_correct"]:
        return layer("failed", "GENERATION_UNSUPPORTED" if case.should_refuse else "WRONG_REFUSAL",
                     scores=scores)
    if not case.should_refuse and scores["required_terms_coverage"] < 1:
        return layer("failed", "GENERATION_INCOMPLETE", scores=scores)
    if not scores["source_overlap"]:
        return layer("failed", "CITATION_SOURCE_WRONG", scores=scores)
    if not scores["citation_present"]:
        return layer("failed", "CITATION_MISSING", scores=scores)
    return layer("passed", "ANSWER_CORRECT", scores=scores)


def waterfall(case, result, trace, mode):
    layers = {"retrieval": analyze_retrieval(case, result, trace)}
    if layers["retrieval"]["status"] == "failed" or mode == "retrieval":
        return layers
    layers["pipeline"] = analyze_pipeline(case, result)
    if layers["pipeline"]["status"] == "failed" or mode == "pipeline":
        return layers
    layers["answer"] = analyze_answer(case, result)
    return layers


def suggested_attribution(layers):
    for result in layers.values():
        if result["status"] == "failed":
            return result["code"]
    return "FIXED" if any(x["status"] == "passed" for x in layers.values()) else "UNATTRIBUTED_NEEDS_REVIEW"


def main():
    ap = argparse.ArgumentParser(description="回放人工批准的 RAG 坏例")
    ap.add_argument("--feedback-id")
    ap.add_argument("--mode", choices=("retrieval", "pipeline", "answer"), default="retrieval")
    ap.add_argument("--allow-llm", action="store_true")
    ap.add_argument("--out-dir", default="output/eval/replay")
    args = ap.parse_args()
    if args.mode in {"pipeline", "answer"} and not args.allow_llm:
        raise SystemExit("pipeline/answer 会使用生产语义规划器，必须显式添加 --allow-llm")
    sql = "SELECT * FROM feedback WHERE status='approved_regression'"
    values = ()
    if args.feedback_id:
        sql += " AND feedback_id=?"; values = (args.feedback_id,)
    with trace_store.connect() as conn:
        cases = [dict(x) for x in conn.execute(sql, values).fetchall()]
    details = []
    metadata = evaluation_metadata()
    for case in cases:
        gold = EvaluationCase.from_mapping(case)
        trace = RAGTrace(case["query"], "replay", code_commit=metadata["git_commit"],
                         index_version=metadata["index_manifest_sha256"])
        result, error = {}, None
        try:
            with observe_llm(trace.record_llm_event):
                if args.mode == "retrieval":
                    hits = rag_search(case["query"], top_k=5, trace=trace)
                    result = {"ok": True, "hits": hits}
                else:
                    result = ask(case["query"], top_k=5,
                                 gen_answer_=args.mode == "answer", trace=trace)
        except Exception as exc:
            error = exc
            result = {"ok": False, "error_type": type(exc).__name__}
        finally:
            trace.finish(result, error)
        layers = waterfall(gold, result, trace, args.mode)
        baseline_trace = trace_store.get_trace(case["trace_id"])
        details.append({
            "feedback_id": case["feedback_id"], "query": case["query"],
            "baseline": {"trace_id": case["trace_id"], "observed_answer": case["observed_answer"],
                         "trace": {key: baseline_trace.get(key) for key in (
                             "route", "intent", "total_ms", "code_commit", "index_version",
                             "model", "prompt_versions_json")}} if baseline_trace else None,
            "candidate": {"trace_id": trace.trace_id, "result": result},
            "layers": layers,
            "suggested_attribution": suggested_attribution(layers),
            "human_confirmation_required": True,
        })
    now = datetime.now(timezone.utc)
    report = {"schema_version": 2, "run_at": now.isoformat(), "metadata": metadata,
              "mode": args.mode, "allow_llm": args.allow_llm, "n": len(details), "details": details}
    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / (now.strftime("%Y%m%dT%H%M%SZ") + "-replay.json")
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"out": str(out.relative_to(ROOT)), "n": len(details)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
