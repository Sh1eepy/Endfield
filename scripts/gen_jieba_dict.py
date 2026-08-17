# -*- coding: utf-8 -*-
"""
gen_jieba_dict.py — 自动生成游戏专有名词 jieba 自定义词典

背景：BM25 检索用 jieba 分词，"重息壤""向心之引"这类专有名词会被切碎
（如"重息壤"→"重""息壤"），导致关键词匹配失败。
本脚本扫描配方库物品名/设备名 + 知识库条目名，凡是 jieba 会切成多段的
名称（长度>=2 且非纯数字）都收进自定义词典。

用法:
    python scripts/gen_jieba_dict.py --out scripts/dict_zh.txt

输出格式（jieba load_userdict 标准）:
    词 词频 词性
"""
import glob
import json
import os
import re
import sys

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

import jieba  # noqa: E402


def collect_names():
    names = set()
    # 配方库：物品名 + 设备名
    rs = (json.load(open(os.path.join(ROOT, "output", "recipes.json"), encoding="utf-8")) or {}).get("recipes", [])
    for r in rs:
        for x in r.get("inputs", []) + r.get("outputs", []):
            n = (x.get("name") or "").strip()
            if n:
                names.add(n)
        m = (r.get("machine") or "").strip()
        if m:
            names.add(m)
    # 知识库条目名
    for f in glob.glob(os.path.join(ROOT, "endfield_kb", "*.jsonl")):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                n = (d.get("name") or "").strip()
                if n:
                    names.add(n)
    return sorted(names)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="scripts/dict_zh.txt")
    args = ap.parse_args()

    names = collect_names()
    print(f"扫描到 {len(names)} 个名称，检查 jieba 切分...")
    kept = []
    for n in names:
        if len(n) < 2 or re.fullmatch(r"[\d\s\-—·.。]+", n):
            continue
        tokens = [t for t in jieba.cut(n) if t.strip()]
        # 切成多段 或 切出的首段不等于整名 → 需要保护
        if len(tokens) > 1:
            kept.append(n)
    # 去重按长度排序（长词优先，jieba 词典内部会处理）
    kept = sorted(set(kept), key=len, reverse=True)
    out_path = os.path.join(ROOT, args.out)
    with open(out_path, "w", encoding="utf-8") as f:
        for k in kept:
            f.write(f"{k} 100 n\n")
    print(f"写入 {len(kept)} 个专有名词 → {args.out}")


if __name__ == "__main__":
    main()
