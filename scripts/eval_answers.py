# -*- coding: utf-8 -*-
"""端到端答案评测：确定性引用/关键词/拒答评分，可选 LLM-as-judge。"""
import argparse
import json
import os
import re
import sys

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def deterministic_score(case, result):
    answer = str(result.get("answer") or "")
    should_refuse = bool(case.get("should_refuse"))
    refused = bool(result.get("rejected")) or "未找到" in answer or "不足" in answer
    terms = case.get("required_terms") or []
    sources = {str(x.get("name") or "") for x in result.get("sources") or []}
    accepted = set(case.get("acceptable_sources") or [])
    return {
        "refusal_correct": refused == should_refuse,
        "required_terms_coverage": round(sum(t in answer for t in terms) / len(terms), 4) if terms else 1.0,
        "citation_present": should_refuse or bool(re.search(r"\[来源\d+\]", answer)),
        "source_overlap": should_refuse or not accepted or bool(sources & accepted),
    }


JUDGE_KEYS = {
    "faithfulness": ("faithfulness", "忠实度"),
    "completeness": ("completeness", "完整性"),
    "relevance": ("relevance", "相关性"),
    "citation_correctness": ("citation_correctness", "引用正确性"),
}


def summarize(details):
    keys = ["refusal_correct", "required_terms_coverage", "citation_present", "source_overlap"]
    summary = {k: round(sum(float(x["deterministic"][k]) for x in details) / len(details), 4) for k in keys}
    judged = []
    for item in details:
        raw = item.get("judge") or {}
        normalized = {}
        for target, aliases in JUDGE_KEYS.items():
            value = next((raw[a] for a in aliases if a in raw), None)
            if isinstance(value, (int, float)):
                normalized[target] = float(value)
        if len(normalized) == len(JUDGE_KEYS):
            item["judge_normalized"] = normalized
            judged.append(normalized)
    summary["judge_coverage"] = round(len(judged) / len(details), 4)
    if judged:
        summary["judge"] = {
            k: round(sum(x[k] for x in judged) / len(judged), 4)
            for k in JUDGE_KEYS
        }
    summary["n"] = len(details)
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", default="output/eval/answer_eval_set.jsonl")
    ap.add_argument("--out", default="output/eval/answer_result.json")
    ap.add_argument("--judge", action="store_true", help="调用已配置 LLM 做 0-2 分忠实度/完整性/相关性/引用评分")
    ap.add_argument("--only", help="只重测查询中包含此文本的样例")
    ap.add_argument("--merge-existing", action="store_true", help="把局部重测结果合并进已有输出")
    args = ap.parse_args()
    from rag_ask import ask
    from llm_client import llm
    cases = [json.loads(x) for x in open(os.path.join(ROOT, args.eval), encoding="utf-8") if x.strip()]
    selected = [c for c in cases if not args.only or args.only in c["query"]]
    details = []
    out = os.path.join(ROOT, args.out)
    if args.merge_existing and os.path.exists(out):
        details = json.load(open(out, encoding="utf-8")).get("details", [])
    replacements = {}
    for case in selected:
        result = ask(case["query"], top_k=5, gen_answer_=True)
        scores = deterministic_score(case, result)
        item = {"query": case["query"], "result": result, "deterministic": scores}
        if args.judge and llm.available() and result.get("answer"):
            prompt = json.dumps({"question": case["query"], "required_terms": case.get("required_terms", []),
                                 "answer": result.get("answer"), "sources": result.get("sources", [])}, ensure_ascii=False)
            try:
                item["judge"] = llm.chat_json(
                    prompt + "\n按忠实度、完整性、相关性、引用正确性分别给0/1/2分，并给reason。",
                    system="你是严格的RAG答案审计员，只输出JSON；没有来源支持的事实不得给忠实度满分。")
            except Exception as exc:
                item["judge_error"] = type(exc).__name__
        replacements[case["query"]] = item
    details = [replacements.pop(x["query"], x) for x in details]
    details.extend(replacements.values())
    summary = summarize(details)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "details": details}, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
