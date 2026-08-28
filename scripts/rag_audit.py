# -*- coding: utf-8 -*-
"""RAG 索引一致性审计：知识库、manifest、Chroma、BM25 与 mention。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_sources(pattern="endfield_kb/*.jsonl"):
    """读取与 build_rag 相同的知识源（分类 JSONL + 干员中文语音）。"""
    from build_rag import load_records
    return load_records(
        [os.path.join(ROOT, pattern)],
        operator_details_path=os.path.join(ROOT, "output", "operator_details.json"),
    )


def audit_index(index_dir="output/rag", check_chroma=True):
    """只读核对知识库、manifest、Chroma、BM25 和 mention 的一致性。"""
    from build_rag import inconsistent_bm25_categories, record_content_hash

    index_dir = index_dir if os.path.isabs(index_dir) else os.path.join(ROOT, index_dir)
    manifest_path = os.path.join(index_dir, "chunks.json")
    issues = []
    try:
        with open(manifest_path, encoding="utf-8") as f:
            manifest = json.load(f)
    except Exception as exc:
        return {"status": "fail", "consistent": False, "issues": [f"manifest_unreadable:{type(exc).__name__}"]}

    kb = _read_sources()
    kb_keys = {(str(x.get("category") or ""), str(x.get("item_id") or "")) for x in kb}
    manifest_keys = {(str(x["meta"].get("category") or ""), str(x["meta"].get("item_id") or "")) for x in manifest}
    stale = 0
    hash_by_key = {}
    for x in manifest:
        hash_by_key[(str(x["meta"].get("category") or ""), str(x["meta"].get("item_id") or ""))] = x.get("hash")
    for x in kb:
        key = (str(x.get("category") or ""), str(x.get("item_id") or ""))
        if hash_by_key.get(key) != record_content_hash(x):
            stale += 1
    if kb_keys != manifest_keys:
        issues.append(f"entry_key_mismatch:kb={len(kb_keys)},manifest={len(manifest_keys)}")
    if stale:
        issues.append(f"stale_entries:{stale}")

    broken = sorted(inconsistent_bm25_categories(manifest, os.path.join(index_dir, "bm25")))
    if broken:
        issues.append("bm25_inconsistent:" + ",".join(broken))

    chroma_count = None
    if check_chroma:
        try:
            import chromadb
            client = chromadb.PersistentClient(path=os.path.join(index_dir, "chroma"))
            chroma_count = client.get_collection("endfield_kb").count()
            if chroma_count != len(manifest):
                issues.append(f"chroma_count_mismatch:{chroma_count}!={len(manifest)}")
        except Exception as exc:
            issues.append(f"chroma_unavailable:{type(exc).__name__}")

    mention_path = os.path.join(ROOT, "output", "mention_index.json")
    if not os.path.exists(mention_path):
        issues.append("mention_index_missing")
    fingerprint = hashlib.sha256("".join(sorted(str(x.get("hash") or "") for x in manifest)).encode()).hexdigest()
    mtime = datetime.fromtimestamp(os.path.getmtime(manifest_path), timezone.utc).isoformat()
    return {
        "status": "ok" if not issues else "degraded", "consistent": not issues,
        "checked_at": datetime.now(timezone.utc).isoformat(), "index_built_at": mtime,
        "source_fingerprint": fingerprint, "kb_entries": len(kb_keys),
        "operator_audio_entries": sum(x.get("source_kind") == "operator_audio" for x in kb),
        "manifest_entries": len(manifest_keys), "manifest_chunks": len(manifest),
        "chroma_chunks": chroma_count, "bm25_inconsistent_categories": broken,
        "issues": issues,
    }


def main():
    """运行索引审计并把结果写入 `output/rag/build_status.json`。"""
    ap = argparse.ArgumentParser()
    ap.add_argument("--index-dir", default="output/rag")
    ap.add_argument("--out", default="output/rag/build_status.json")
    ap.add_argument("--no-chroma", action="store_true")
    ap.add_argument("--fail-on-error", action="store_true")
    args = ap.parse_args()
    result = audit_index(args.index_dir, check_chroma=not args.no_chroma)
    out = args.out if os.path.isabs(args.out) else os.path.join(ROOT, args.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.fail_on_error and not result["consistent"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
