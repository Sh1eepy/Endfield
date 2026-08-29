"""RAG 运行配置的单一来源；构建、检索、Trace 与评测必须从这里读取。"""
import os


DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"
DEFAULT_LLM_MODEL = "deepseek-chat"

EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip()
LLM_MODEL = os.environ.get("LLM_MODEL", DEFAULT_LLM_MODEL).strip()

BM25_TOP_N = 20
VECTOR_TOP_N = 20
NAME_TOP_N_MIN = 10
RRF_K = 60
FINAL_TOP_K = 5


def retrieval_config():
    return {
        "bm25_top_n": BM25_TOP_N,
        "vector_top_n": VECTOR_TOP_N,
        "name_top_n_min": NAME_TOP_N_MIN,
        "rrf_k": RRF_K,
        "final_top_k": FINAL_TOP_K,
    }
