# -*- coding: utf-8 -*-
"""
gen_eval_set.py — RAG 评测集自动生成器（RAG_UPGRADE_PLAN.md 阶段 1）

思路：用在线 LLM 按「意图类别 × 难度」矩阵自动生成查询，gold 答案用
结构化配方库 / 知识库自动核对（不是让 LLM 编答案，避免"自问自答"污染评测）。

用法:
    python scripts/gen_eval_set.py --per-class 6 --out output/eval/eval_set.jsonl

输出（JSONL）:
    {"query": "...", "intent": "配方", "difficulty": "简单",
     "gold_names": ["重息壤"], "relevance": 2, "source": "auto", "anchor": "重息壤"}

难度定义:
    简单: 字面包含物品全名（"重息壤怎么合成"）
    中等: 同义改写，含核心词（"息壤怎么造"）
    困难: 口语化描述，仅含物品名 2-4 字核心片段（"这玩意儿怎么弄出来"）

类别（intent）: 配方 / 设备 / 知识 / 比较 / 数值

关键约束（自动核对）:
    - 配方类: anchor 必须是 recipes.json 中的可制造物品（出现于 outputs）
    - 设备类: anchor 必须是 recipes.json 中的机器名
    - 知识类: anchor 必须是知识库条目（非配方物品优先）
    - 比较类: 随机配对两个 anchor，gold 为两者
    - 数值类: anchor 条目 sections 需含数值特征
    - LLM 生成的查询必须包含 anchor 的 core（核心片段），不满足的丢弃并补生成

未配置 LLM_API_KEY 时：降级为模板生成（简单+中等用规则模板，困难跳过），仍可产出初版。
"""
import argparse
import glob
import json
import os
import random
import re
import sys

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from llm_client import llm  # noqa: E402

random.seed(42)

PROMPT_TMPL = """你是《明日方舟：终末地》资深玩家，帮评测系统生成搜索查询。
针对目标{anchor_desc}生成 3 条中文自然问句（用户可能真的会这样搜索）：

1. 简单：直接包含目标全名，问法直白（如"X怎么合成"）
2. 中等：同义改写，不出现完整全名但保留核心词（如"铁零件怎么来的"）
3. 困难：口语化/模糊描述，只包含目标名字的 {core_len} 字核心片段（如"能装水的罐子"）

硬性要求：
- 3 条必须互相不同、都是独立自然问句
- 每条都必须包含目标名的核心片段（连续子串），否则判为废题
- 不要编造目标不存在的功能

输出严格 JSON（不要多余文字）:
{{"core": "核心片段(目标名连续子串)", "queries": [
  {{"difficulty": "简单", "query": "..."}},
  {{"difficulty": "中等", "query": "..."}},
  {{"difficulty": "困难", "query": "..."}}
]}}"""


# ===================== 数据加载 =====================

def load_recipes(path):
    rs = json.load(open(path, encoding="utf-8"))
    rs = rs if isinstance(rs, list) else rs.get("recipes", rs)
    return rs


def load_kb(patterns):
    recs = []
    for p in patterns:
        for f in sorted(glob.glob(p)):
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    recs.append(d)
    return recs


def anchor_specs(recipes, kb):
    """构造五类锚点。"""
    # 配方类：可制造物品（出现在 outputs 中），排除基础资源名
    base = {"清水", "惰气", "息壤气", "水蒸气", "酸气", "沉积酸"}
    made = []
    seen = set()
    for r in recipes:
        for o in r["outputs"]:
            n = o["name"].strip()
            if n not in base and n not in seen:
                made.append((n, o["item_id"]))
                seen.add(n)
    machines = sorted({r["machine"].strip() for r in recipes if r.get("machine")})
    # 知识类：非配方物品的知识条目（干员/武器/装备/任务等）
    made_names = {n for n, _ in made}
    kb_items = [r for r in kb if r.get("name") and r["name"].strip() not in made_names]
    # 数值类：条目 sections 疑似含数值（% / 数字+单位）
    num_items = [r for r in kb_items if re.search(r"\d+[%％]|\d+\.\d", (r.get("full_text") or ""))]
    return {
        "配方": [{"kind": "物品", "name": n, "id": i} for n, i in made],
        "设备": [{"kind": "设备", "name": m, "id": ""} for m in machines],
        "知识": [{"kind": "条目", "name": r["name"].strip(), "id": str(r.get("item_id") or ""),
                  "cat": r.get("category", "")} for r in kb_items],
        "数值": [{"kind": "条目", "name": r["name"].strip(), "id": str(r.get("item_id") or ""),
                  "cat": r.get("category", "")} for r in num_items],
        "比较": [{"kind": "条目", "name": r["name"].strip(), "id": str(r.get("item_id") or ""),
                  "cat": r.get("category", "")} for r in kb_items],
    }


# ===================== 生成 =====================

def sample_anchors(specs, per_class):
    out = {}
    for intent, items in specs.items():
        random.shuffle(items)
        picked = items[:per_class]
        if intent == "比较":
            # 比较类：同类配对（同 category 才配对，避免"头像vsPV"这种无意义比较），
            # 且尽量选同分类下相邻条目（语义相近更好比）
            by_cat = {}
            for it in items:
                by_cat.setdefault(it.get("cat", ""), []).append(it)
            pairs = []
            for cat, lst in by_cat.items():
                if len(lst) < 2:
                    continue
                random.shuffle(lst)
                for i in range(0, len(lst) - 1, 2):
                    pairs.append({"kind": "比较对", "a": lst[i], "b": lst[i + 1]})
                    if len(pairs) >= per_class:
                        break
                if len(pairs) >= per_class:
                    break
            picked = pairs[:per_class]
        out[intent] = picked
    return out


def anchor_desc(a):
    if a["kind"] == "比较对":
        return f"「{a['a']['name']}」与「{a['b']['name']}」（比较两者哪个更好/有何区别）"
    return f"「{a['name']}」"


def gen_one(llm_enabled, a):
    """生成一个锚点的 3 条查询。返回 (core, [(difficulty, query)...]) 或 None。"""
    core_len = 4 if a["kind"] != "比较对" else 3
    prompt = PROMPT_TMPL.format(anchor_desc=anchor_desc(a), core_len=core_len)
    if llm_enabled:
        try:
            d = llm.chat_json(prompt, temperature=0.7, max_tokens=600)
            core = str(d.get("core") or "").strip()
            qs = []
            for q in (d.get("queries") or []):
                diff = str(q.get("difficulty") or "").strip()
                query = str(q.get("query") or "").strip()
                if diff and query and core:
                    qs.append((diff, query))
            if len(qs) >= 2 and core:
                return core, qs
        except Exception as e:
            print(f"  [LLM失败] {e.__class__.__name__}: {e}")
            return None
    # 降级：规则模板（简单+中等），困难跳过
    return None


def template_fallback(a):
    """无 LLM 时的规则模板题（简单+中等）。"""
    name = a.get("name") or (a["a"]["name"] if a["kind"] == "比较对" else "")
    if not name:
        return []
    core = name[:4]
    if a["kind"] == "比较对":
        b = a["b"]["name"]
        return [(core, [("简单", f"{name}和{b}哪个好"), ("中等", f"{name}和{b}有何区别")])]
    return [(core, [("简单", f"{name}怎么合成"), ("中等", f"{name}怎么来的")])]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--recipes", default="output/recipes.json")
    ap.add_argument("--kb", nargs="*", default=["endfield_kb/*.jsonl"])
    ap.add_argument("--out", default="output/eval/eval_set.jsonl")
    ap.add_argument("--per-class", type=int, default=6, help="每类锚点数（比较类=配对数）")
    args = ap.parse_args()

    recipes = load_recipes(os.path.join(ROOT, args.recipes))
    kb = load_kb([os.path.join(ROOT, p) for p in args.kb])
    print(f"配方 {len(recipes)} | 知识条目 {len(kb)}")

    specs = anchor_specs(recipes, kb)
    for intent, items in specs.items():
        print(f"  {intent}: 可用锚点 {len(items)}")

    picked = sample_anchors(specs, args.per_class)
    llm_enabled = llm.available()
    print(f"LLM: {'启用（在线生成）' if llm_enabled else '未配置 → 规则模板降级（仅简单/中等）'}")

    os.makedirs(os.path.dirname(os.path.join(ROOT, args.out)), exist_ok=True)
    rows, stats = [], {"配方": 0, "设备": 0, "知识": 0, "比较": 0, "数值": 0}
    total_attempt = 0

    for intent in ["配方", "设备", "知识", "数值", "比较"]:
        for a in picked[intent]:
            total_attempt += 1
            res = gen_one(llm_enabled, a)
            if not res and not llm_enabled:
                res = None
                for core, qs in template_fallback(a):
                    res = (core, qs)
            if not res:
                print(f"  [{intent}] 跳过锚点: {anchor_desc(a)}（生成失败）")
                continue
            core, qs = res
            gold_names = ([a["name"]] if a["kind"] != "比较对" else [a["a"]["name"], a["b"]["name"]])
            for diff, query in qs:
                # 硬校验：查询必须包含 core（自动核对，防 LLM 跑题）
                if core and core not in query:
                    continue
                rows.append({"query": query, "intent": intent, "difficulty": diff,
                             "gold_names": gold_names, "relevance": 2,
                             "source": "auto", "anchor": gold_names[0], "core": core})
                stats[intent] += 1

    out_path = os.path.join(ROOT, args.out)
    with open(out_path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"\n生成完成: {len(rows)} 条 → {args.out}")
    for k, v in stats.items():
        print(f"  {k}: {v}")
    print(f"锚点尝试: {total_attempt}（含失败跳过）")


if __name__ == "__main__":
    main()
