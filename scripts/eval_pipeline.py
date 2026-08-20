# -*- coding: utf-8 -*-
"""评测意图分类与实际问答路由；默认禁用在线 LLM，结果落盘。"""
import argparse
import json
import os
import sys

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def main():
    """离线评估意图分类覆盖率和实际路由，不默认调用在线 LLM。"""
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", default="output/eval/routing_eval_set.jsonl")
    ap.add_argument("--out", default="output/eval/pipeline_result.json")
    ap.add_argument("--allow-llm", action="store_true")
    args = ap.parse_args()
    from intent_router import classify_batch, llm as router_llm
    from rag_ask import ask, llm as ask_llm
    if not args.allow_llm:
        router_llm.api_key = ""
        ask_llm.api_key = ""
    rows = [json.loads(x) for x in open(os.path.join(ROOT, args.eval), encoding="utf-8") if x.strip()]
    predictions = classify_batch([row["query"] for row in rows])
    # 路由评测保持无生成、无在线改写，避免把网络波动混进确定性路由指标。
    ask_llm.api_key = ""
    expected_routes = {"配方": {"structured"}, "设备": {"structured", "rag"},
                       "知识": {"rag"}, "比较": {"rag"}, "数值": {"rag"}}
    details, intent_ok, route_ok = [], 0, 0
    for row in rows:
        pred, confidence, method = predictions[row["query"]]
        result = ask(row["query"], top_k=5, gen_answer_=False)
        route = result.get("route_used")
        i_ok = pred == row.get("intent")
        expected = row.get("expected_route")
        r_ok = route == expected if expected else route in expected_routes.get(row.get("intent"), {route})
        intent_ok += i_ok
        route_ok += r_ok
        details.append({"query": row["query"], "gold_intent": row.get("intent"),
                        "pred_intent": pred, "intent_method": method, "confidence": confidence,
                        "route_used": route, "intent_ok": i_ok, "route_ok": r_ok})
    classified = [x for x in details if x["pred_intent"]]
    summary = {"n": len(rows), "intent_accuracy": round(intent_ok / len(rows), 4),
               "classified_rate": round(len(classified) / len(rows), 4),
               "accuracy_on_classified": round(sum(x["intent_ok"] for x in classified) / len(classified), 4) if classified else 0.0,
               "route_accuracy": round(route_ok / len(rows), 4), "llm_enabled": args.allow_llm}
    out = os.path.join(ROOT, args.out)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "details": details}, f, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
