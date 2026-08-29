# -*- coding: utf-8 -*-
"""
eval_retrieval.py — RAG 严格检索评测

用法:
    python scripts/eval_retrieval.py                          # 用默认评测集
    python scripts/eval_retrieval.py --eval output/eval/eval_set.jsonl --out output/eval/baseline.json

指标:
    Recall@k: top-k 中是否命中 gold（按条）
    MRR:      第一个 gold 命中的倒数排名
    Precision@k: top-k 中相关占比（relevance>=1 即相关）

命中判定（严格，不搞子串放水）:
    - 配方/设备/知识/数值类: 结果的 name 与 gold_names 之一相等，
      或互为包含（"重息壤" vs "重息壤"、"中容谷地电池" vs "电池"——后者仅当 gold 本身是简称）
    - 比较类: 两个 gold 都命中才算

输出: 全量指标 + 按 意图×难度 分表 → JSON 存档。
"""
import argparse
import json
import os
import sys

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))


def _norm(s):
    """名称归一化：全角→半角、去引号/空格/括号差异，避免字符形态导致误判。"""
    s = (s or "").strip()
    for f, t in [("（", "("), ("）", ")"), ("，", ","), ("：", ":"), ("　", " "),
                 ("“", '"'), ("”", '"'), ("『", "["), ("』", "]")]:
        s = s.replace(f, t)
    s = s.replace('"', "").replace("'", "").replace(" ", "")
    return s


def hit_name(res_name, gold):
    """严格命中：归一化后相等或互为包含（防子串放水——gold 为简称如"电池"时允许包含）。"""
    rn = _norm(res_name)
    g = _norm(gold)
    if not rn or not g:
        return False
    if rn == g:
        return True
    # 仅当 gold 是简称（len<=6 且非完整名）时允许包含；避免"赫铜"命中"气态赫铜"这种误判
    return g in rn and len(g) <= 6


def judged(row, results, recipes_ix):
    """判定一条查询是否命中。返回 (hit, first_rank_or_None)。"""
    golds = row.get("gold_names") or []
    if not golds:
        return False, None
    ranks = []
    for rank, h in enumerate(results, 1):
        name = h["meta"].get("name") or ""
        iid = str(h["meta"].get("item_id") or "")
        # 配方类 gold 可能在 recipes.json 里是正式名，知识库 name 也允许
        for g in golds:
            if hit_name(name, g):
                ranks.append(rank)
                break
    if row.get("intent") == "比较":
        # 比较类：两个 gold 都要命中；允许"系列命中"——查询用简称（如"跨过寰宇深处"）
        # 而 gold 是系列子项（"跨过寰宇深处·二"）时，检索结果若命中同一系列（前缀匹配）
        # 也算命中（用户在问整个系列，不精确到子节）。
        for g in golds:
            gnorm = _norm(g)
            hit_g = any(hit_name(h["meta"].get("name") or "", g) for h in results)
            if not hit_g and gnorm:
                # 系列匹配：gold 的"前缀"（去掉 ·序号 后缀）出现在某结果中
                prefix = gnorm.split("·")[0].split("-")[0].strip()
                if len(prefix) >= 3:
                    hit_g = any(prefix in _norm(h["meta"].get("name") or "") for h in results)
            if not hit_g:
                return False, None
        # 两个都命中：取最早的 gold 命中位次做 MRR
        first = min((r for r in ranks), default=None)
        return True, first
    first = min(ranks, default=None)
    return first is not None, first


def main():
    """运行严格检索集并按意图、难度汇总 Recall、MRR 和 Precision。"""
    ap = argparse.ArgumentParser()
    ap.add_argument("--eval", default="output/eval/eval_set.jsonl")
    ap.add_argument("--out", default="output/eval/result.json")
    ap.add_argument("--top-k", type=int, default=5)
    ap.add_argument("--index-dir", default="output/rag")
    args = ap.parse_args()

    from rag_search import RAGRetriever
    from recipe_index import load_recipes, build_item_index
    from build_eval_manifest import evaluation_metadata

    recipes = load_recipes(os.path.join(ROOT, "output", "recipes.json"))
    recipes_ix = build_item_index(recipes)

    print("加载检索器（离线）...", flush=True)
    retriever = RAGRetriever(os.path.join(ROOT, args.index_dir))
    print("加载完成。", flush=True)

    rows = [json.loads(l) for l in open(os.path.join(ROOT, args.eval), encoding="utf-8") if l.strip()]
    print(f"评测集: {len(rows)} 条\n", flush=True)

    # 按 (intent, difficulty) 分组统计
    groups = {}
    for row in rows:
        key = (row.get("intent"), row.get("difficulty"))
        groups.setdefault(key, {"total": 0, "hit": 0, "rr": 0.0, "prec": 0.0})
    details = []
    for row in rows:
        results = retriever.search(row["query"], top_k=args.top_k)
        hit, first = judged(row, results, recipes_ix)
        key = (row.get("intent"), row.get("difficulty"))
        g = groups[key]
        g["total"] += 1
        g["hit"] += 1 if hit else 0
        g["rr"] += (1.0 / first) if first else 0.0
        # Precision@k: top-k 中与 gold 相关的占比（近似：name 命中 gold 之一）
        rel = sum(1 for h in results if any(hit_name(h["meta"].get("name") or "", gg) for gg in (row.get("gold_names") or [])))
        g["prec"] += rel / args.top_k
        details.append({"query": row["query"], "intent": key[0], "difficulty": key[1],
                        "hit": hit, "first_rank": first,
                        "top_names": [h["meta"].get("name") for h in results]})

    # 汇总
    print("=" * 60)
    print(f"RAG 检索评测（top-k={args.top_k}, 严格命中判定）")
    print("=" * 60)
    summary = {"intents": {}, "overall": {}}
    for key in sorted(groups):
        g = groups[key]
        recall = g["hit"] / g["total"]
        mrr = g["rr"] / g["total"]
        prec = g["prec"] / g["total"]
        print(f"  [{key[0]}/{key[1]}] n={g['total']} Recall@{args.top_k}={recall:.0%} MRR={mrr:.3f} P@{args.top_k}={prec:.3f}")
        summary["intents"].setdefault(key[0], {})[key[1]] = {
            "n": g["total"], "recall": round(recall, 4), "mrr": round(mrr, 4), "precision": round(prec, 4)}
    tot_hit = sum(g["hit"] for g in groups.values())
    tot_n = sum(g["total"] for g in groups.values())
    tot_rr = sum(g["rr"] for g in groups.values())
    tot_prec = sum(g["prec"] for g in groups.values())
    summary["overall"] = {
        "n": tot_n, "recall": round(tot_hit / tot_n, 4),
        "mrr": round(tot_rr / tot_n, 4), "precision": round(tot_prec / tot_n, 4)}
    print("-" * 60)
    print(f"  总体: n={tot_n} Recall@{args.top_k}={summary['overall']['recall']:.0%} "
          f"MRR={summary['overall']['mrr']:.3f} P@{args.top_k}={summary['overall']['precision']:.3f}")
    print("=" * 60)

    out_path = os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"metadata": evaluation_metadata(), "summary": summary, "details": details},
                  f, ensure_ascii=False, indent=1)
    print(f"已存档: {args.out}")


if __name__ == "__main__":
    main()
