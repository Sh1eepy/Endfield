# -*- coding: utf-8 -*-
"""
rag_search.py — 混合检索（向量语义 + BM25 关键词 → RRF 融合）

CLI 用法:
    python scripts/rag_search.py "什么设备能辅助攻击"
    python scripts/rag_search.py "制造重息壤气" --top-k 5
    python scripts/rag_search.py "赤铜耐压罐" --json          # 输出 JSON（供 RAG 系统集成）

模块用法:
    from rag_search import RAGRetriever
    retriever = RAGRetriever()                       # 默认加载 output/rag
    results = retriever.search("查询", top_k=5)
    # results: [{meta:{item_id,name,category,...}, text, score, vector_score, bm25_score}]

检索方式: 向量 top-N + BM25 top-N 双路召回，Reciprocal Rank Fusion 融合排序。
"""
import argparse
import json
import os
import pickle
import re
import sys
from contextlib import nullcontext

try:
    from scripts.rag_config import (BM25_TOP_N, EMBEDDING_MODEL, NAME_TOP_N_MIN, RRF_K,
                                    VECTOR_TOP_N)
except ModuleNotFoundError:  # `python scripts/rag_search.py`
    from rag_config import (BM25_TOP_N, EMBEDDING_MODEL, NAME_TOP_N_MIN, RRF_K,
                            VECTOR_TOP_N)

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")

# 离线模式：模型已缓存，禁止联网检查 HF（否则会超时失败）
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

BGE_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："

_DICT_LOADED = False


def _load_userdict():
    """加载项目自定义 jieba 词典（与 build_rag 保持一致的分词）。"""
    global _DICT_LOADED
    if _DICT_LOADED:
        return
    import jieba
    dict_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "scripts", "dict_zh.txt")
    if os.path.exists(dict_path):
        with open(dict_path, encoding="utf-8") as f:
            jieba.load_userdict(f)
    _DICT_LOADED = True


class RAGRetriever:
    """加载本地索引，执行名称、BM25、向量三路召回并用 RRF 合并。"""
    def __init__(self, index_dir="output/rag", model_name=EMBEDDING_MODEL):
        self.index_dir = index_dir
        # ---------- 加载 BM25（按分类分片，跨分片合并）----------
        import glob as _glob

        bm25_dir = os.path.join(index_dir, "bm25")
        self.bm25_shards = []          # [(BM25, 全局起点)]
        self.chunk_texts, self.metas = [], []
        shard_files = sorted(_glob.glob(os.path.join(bm25_dir, "*.pkl"))) if os.path.isdir(bm25_dir) else []
        if not shard_files and os.path.exists(os.path.join(index_dir, "bm25.pkl")):
            shard_files = [os.path.join(index_dir, "bm25.pkl")]  # 旧版单一文件兼容
        for f in shard_files:
            with open(f, "rb") as fh:
                data = pickle.load(fh)
            self.bm25_shards.append((data["bm25"], len(self.chunk_texts)))
            self.chunk_texts.extend(data["chunk_texts"])
            self.metas.extend(data["metas"])
        # ---------- 加载向量库 ----------
        import chromadb
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name, local_files_only=True)
        self.client = chromadb.PersistentClient(path=os.path.join(index_dir, "chroma"))
        self.coll = self.client.get_collection("endfield_kb")

    # ---------- BM25 检索（跨分片）----------
    def bm25_search(self, query, top_n):
        import jieba

        _load_userdict()
        tokens = [t for t in jieba.cut(query) if t.strip() and t.strip() != "\n"]
        if not tokens or not self.bm25_shards:
            return []
        candidates = []
        for bm25, base in self.bm25_shards:
            scores = bm25.get_scores(tokens)
            order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_n]
            for i in order:
                if scores[i] > 0:
                    candidates.append((float(scores[i]), base + i))
        candidates.sort(key=lambda x: -x[0])
        return [(i, s) for s, i in candidates[:top_n]]

    # ---------- 向量检索 ----------
    def vector_search(self, query, top_n):
        qv = self.model.encode(
            [BGE_QUERY_INSTRUCTION + query],
            normalize_embeddings=True,
        ).tolist()
        res = self.coll.query(query_embeddings=qv, n_results=min(top_n, self.coll.count()))
        ids, dists = res["ids"][0], res["distances"][0]
        idx_map = {f"{m['category']}-{m['item_id']}-{m['chunk_index']}": i for i, m in enumerate(self.metas)}
        out = []
        for cid, d in zip(ids, dists):
            i = idx_map[cid]
            out.append((i, float(1.0 - d)))  # cosine 距离转相似度
        return out

    # ---------- 条目名称召回 ----------
    def name_search(self, query, top_n):
        """按条目名称核心词召回，弥补“定档PV/清淤/佩丽卡怎么玩”等短名查询。"""
        import jieba

        _load_userdict()
        q = re.sub(r"[\s·・:：,，。！？?!《》【】()（）\-]", "", query).lower()
        intent_tokens = {"攻略", "玩家攻略", "角色攻略", "怎么玩", "怎么用", "配队", "养成", "视频", "哪里看", "在哪看", "pv"}
        q_tokens = {t.strip().lower() for t in jieba.cut(query)
                    if len(t.strip()) >= 2 and t.strip().lower() not in intent_tokens}
        wants_guide = any(x in query for x in ("攻略", "怎么玩", "怎么用", "配队", "养成"))
        wants_video = any(x.lower() in query.lower() for x in ("pv", "视频", "哪里看", "在哪看"))
        candidates = []
        for i, meta in enumerate(self.metas):
            name = str(meta.get("name") or "")
            category = str(meta.get("category") or "")
            n = re.sub(r"[\s·・:：,，。！？?!《》【】()（）\-]", "", name).lower()
            if not n:
                continue
            name_tokens = {t.strip().lower() for t in jieba.cut(name)
                           if len(t.strip()) >= 2 and t.strip().lower() not in intent_tokens}
            overlap = q_tokens & name_tokens
            core = n
            if "攻略" in category:
                core = core.replace("玩家攻略", "").replace("攻略", "")
            if "视频" in category and core.startswith("游戏"):
                core = core[2:]
            core_match = len(core) >= 2 and core in q
            contained = n in q or core_match or any(len(t) >= 2 and t in n for t in q_tokens)
            if not contained and not overlap:
                continue
            score = (8.0 if n in q else 0.0) + (20.0 if core_match else 0.0) + sum(len(t) for t in overlap)
            if wants_guide and "攻略" in category:
                score += 12.0
            if wants_video and "视频" in category:
                score += 6.0
            candidates.append((i, score))
        candidates.sort(key=lambda x: (-x[1], len(str(self.metas[x[0]].get("name") or ""))))
        return candidates[:top_n]

    # ---------- RRF 融合 ----------
    @staticmethod
    def rrf_fuse(*ranked_lists, k=RRF_K):
        scores = {}
        for ranked in ranked_lists:
            for rank, (i, _s) in enumerate(ranked):
                scores[i] = scores.get(i, 0.0) + 1.0 / (k + rank + 1)
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)

    def search(self, query, top_k=5, bm25_top_n=BM25_TOP_N,
               vec_top_n=VECTOR_TOP_N, fuse_k=RRF_K, trace=None):
        with trace.span("bm25_retrieval") if trace else nullcontext():
            bm25_hits = self.bm25_search(query, bm25_top_n)
        with trace.span("vector_retrieval") if trace else nullcontext():
            vec_hits = self.vector_search(query, vec_top_n)
        with trace.span("name_retrieval") if trace else nullcontext():
            name_hits = self.name_search(query, max(top_k, NAME_TOP_N_MIN))
        if trace:
            def channel_hits(ranked, score_key):
                return [{"meta": self.metas[i], "score": score, score_key: score}
                        for i, score in ranked]
            trace.record_retrieval("bm25", channel_hits(bm25_hits, "bm25_score"), query)
            trace.record_retrieval("vector", channel_hits(vec_hits, "vector_sim"), query)
            trace.record_retrieval("name", channel_hits(name_hits, "name_score"), query)
        vec_score = dict(vec_hits)
        bm25_score = dict(bm25_hits)
        with trace.span("rrf_fusion") if trace else nullcontext():
            fused = self.rrf_fuse(bm25_hits, vec_hits, name_hits, k=fuse_k)
        # 明确的攻略/视频请求中，名称+分类是强证据；只提升名称通道第一名，避免影响普通配方查询。
        explicit_name_intent = any(x in query for x in ("攻略", "怎么玩", "怎么用", "配队", "养成", "视频", "哪里看", "在哪看")) or "pv" in query.lower()
        if explicit_name_intent and name_hits:
            preferred = name_hits[0][0]
            fused = [(preferred, dict(fused).get(preferred, 0.0))] + [x for x in fused if x[0] != preferred]
        results = []
        for i, score in fused[:top_k]:
            m = self.metas[i]
            results.append(
                {
                    "meta": m,
                    "text": self.chunk_texts[i],
                    "score": round(score, 5),
                    "vector_sim": round(vec_score.get(i, 0.0), 5),
                    "bm25_score": round(bm25_score.get(i, 0.0), 5),
                }
            )
        if trace:
            trace.record_retrieval("rrf", results, query)
        return results


def main():
    """命令行检索入口，用于快速检查召回结果和分数。"""
    ap = argparse.ArgumentParser(description="混合检索：向量 + BM25 → RRF")
    ap.add_argument("query", help="查询语句")
    ap.add_argument("--top-k", type=int, default=5, help="返回条数")
    ap.add_argument("--index-dir", default="output/rag", help="索引目录")
    ap.add_argument("--model", default=EMBEDDING_MODEL, help="embedding 模型名")
    ap.add_argument("--json", action="store_true", help="以 JSON 输出（供系统集成）")
    args = ap.parse_args()

    r = RAGRetriever(args.index_dir, args.model)
    results = r.search(args.query, top_k=args.top_k)

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    print(f"查询: {args.query}\n")
    for rank, hit in enumerate(results, 1):
        m = hit["meta"]
        print(
            f"[{rank}] ({m['category']}) {m['name']}  #ID {m['item_id']} "
            f"RRF={hit['score']} 向量={hit['vector_sim']} BM25={hit['bm25_score']}"
        )
        print("  " + hit["text"].replace("\n", "\n  ")[:400])
        print()


if __name__ == "__main__":
    main()
