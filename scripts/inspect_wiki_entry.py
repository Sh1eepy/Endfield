# -*- coding: utf-8 -*-
"""审计单个 WIKI 条目的原始文档/组件结构，结果写 UTF-8 JSON。"""
import argparse
import glob
import json
import os


def compact(value, depth=0):
    """限制深度和样本数量，生成便于阅读的条目结构摘要。"""
    if depth > 4:
        return type(value).__name__
    if isinstance(value, dict):
        return {k: compact(v, depth + 1) for k, v in value.items()
                if k not in {"blockMap", "cellMap"}}
    if isinstance(value, list):
        return [compact(x, depth + 1) for x in value[:12]]
    if isinstance(value, str):
        return value[:300]
    return value


def main():
    """按名称检查原始 WIKI 条目，帮助定位解析问题。"""
    ap = argparse.ArgumentParser()
    ap.add_argument("name")
    ap.add_argument("--input")
    ap.add_argument("--out", default="logs/wiki_entry_structure.json")
    args = ap.parse_args()
    fname = args.input or sorted(glob.glob("endfield_wiki_full_*.json"))[-1]
    with open(fname, encoding="utf-8") as f:
        data = json.load(f)
    entry = next((x for x in data["catalog"] if (x.get("item") or {}).get("name") == args.name), None)
    if not entry:
        raise SystemExit(f"未找到条目: {args.name}")
    doc = (((entry.get("detail") or {}).get("item") or {}).get("document") or {})
    documents = {}
    for key, value in (doc.get("documentMap") or {}).items():
        blockmap = value.get("blockMap") or {}
        documents[key] = {
            "block_ids": value.get("blockIds") or [],
            "block_kinds": [((blockmap.get(x) or {}).get("kind")) for x in value.get("blockIds") or []],
            "block_samples": [compact(blockmap.get(x) or {}) for x in (value.get("blockIds") or [])[:5]],
        }
    result = {
        "name": args.name,
        "item_id": str((entry.get("item") or {}).get("itemId") or ""),
        "chapter_group": compact(doc.get("chapterGroup") or []),
        "widget_common_map": compact(doc.get("widgetCommonMap") or {}),
        "extra_info": compact(doc.get("extraInfo") or {}),
        "documents": documents,
        "audio_lists": {
            f"{widget_id}:{tab_id}": compact(tab.get("audioList") or [])
            for widget_id, widget in (doc.get("widgetCommonMap") or {}).items()
            for tab_id, tab in (widget.get("tabDataMap") or {}).items()
            if tab.get("audioList")
        },
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
