"""生成评测版本清单；只读取仓库文件，不调用模型或网络。"""
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
import sys
sys.path.insert(0, str(ROOT / "scripts"))

from rag_config import EMBEDDING_MODEL, retrieval_config  # noqa: E402
from rag_prompts import PROMPT_VERSIONS  # noqa: E402
DATASETS = {
    "retrieval": "output/eval/eval_set.jsonl",
    "routing": "output/eval/routing_eval_set.jsonl",
    "answer": "output/eval/answer_eval_set.jsonl",
    "graph": "output/eval/graph_eval_set.jsonl",
}


def text_sha256(path):
    """对文本内容统一换行后哈希，避免 Windows CRLF 与 Linux LF 让 CI 假性失效。"""
    normalized = path.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


def git_dirty():
    try:
        return bool(subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, text=True).strip())
    except (OSError, subprocess.SubprocessError):
        return None


def build_manifest():
    """生成可跨机器复现的离线基线；运行时模型/Git 状态写入每次评测元数据。"""
    datasets = {}
    for name, rel in DATASETS.items():
        path = ROOT / rel
        datasets[name] = {"path": rel, "sha256": text_sha256(path),
                          "rows": sum(bool(x.strip()) for x in path.read_text(encoding="utf-8").splitlines())}
    manifest_path = ROOT / "output" / "rag" / "chunks.json"
    comparable = {
        "schema_version": 2,
        "index_manifest_sha256": text_sha256(manifest_path),
        "embedding_model": EMBEDDING_MODEL,
        "prompt_versions": PROMPT_VERSIONS,
        "retrieval": retrieval_config(),
        "datasets": datasets,
        "sets": {"dev": ["retrieval", "routing"], "holdout": [], "challenge": [],
                 "production_sample": []},
        "privacy": {"ordinary_trace_query": "sha256+length",
                    "feedback_query": "explicit_user_submission"},
    }
    encoded = json.dumps(comparable, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":")).encode("utf-8")
    return {**comparable, "manifest_id": "sha256:" + hashlib.sha256(encoded).hexdigest(),
            "generated_at": datetime.now(timezone.utc).isoformat()}


def evaluation_metadata():
    from llm_client import llm
    manifest = build_manifest()
    return {"manifest_id": manifest["manifest_id"], "git_commit": git_commit(),
            "git_dirty": git_dirty(), "llm_model": llm.model,
            "index_manifest_sha256": manifest["index_manifest_sha256"],
            "prompt_versions": manifest["prompt_versions"], "retrieval": manifest["retrieval"]}


def main():
    manifest = build_manifest()
    out = ROOT / "output" / "eval" / "eval_manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
