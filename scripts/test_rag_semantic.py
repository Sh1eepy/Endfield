# -*- coding: utf-8 -*-
"""测试：口语化描述 → RAG 能否定位精确物品（语义理解层场景）。"""
import os, sys, json
if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))

from rag_search import RAGRetriever

r = RAGRetriever("output/rag", "BAAI/bge-small-zh-v1.5")

queries = [
    ("中等容量的电池", ["中容谷地电池", "中容武陵电池"]),
    ("造重息壤的机器", ["天有洪炉", "固气转化机"]),
    ("能种农作物的设备", ["种植机"]),
    ("红色的金属块", ["赤铜块"]),
    ("做电池需要的那种小零件", ["铁制零件", "赫铜零件"]),
]

out = []
for q, targets in queries:
    hits = r.search(q, top_k=3)
    names = [h["meta"]["name"] for h in hits]
    hit = next((t for t in targets if t in names), None)
    out.append({"query": q, "targets": targets, "hit": hit, "top3": names})
    print(f"查询: {q} | 目标: {targets} | 命中: {hit or '✗'}")
    for h in hits[:3]:
        print(f"   [{h['meta']['name']}] 向量={h['vector_sim']:.3f} BM25={h['bm25_score']:.1f}")

with open("output/rag_semantic_test.json", "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1)
print("\nDone")
