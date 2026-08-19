# -*- coding: utf-8 -*-
"""从原始 WIKI 构建干员详情结构库（Tab、富文本样式、图片与音频）。"""
import argparse
import glob
import json
import os
import sys

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")

from build_kb_all import build_id2name, render_document_struct, render_inline


def clean_audio(item):
    url = str(item.get("resourceUrl") or "").strip()
    if not url:
        return None
    return {"id": str(item.get("id") or ""), "title": str(item.get("title") or "语音"),
            "profile": str(item.get("profile") or ""), "url": url}


def build_operator(entry, id2name):
    item = entry.get("item") or {}
    detail_item = (entry.get("detail") or {}).get("item") or {}
    doc = detail_item.get("document") or {}
    docmap = doc.get("documentMap") or {}
    rendered = {key: render_document_struct(value, id2name) for key, value in docmap.items()}
    widgets = doc.get("widgetCommonMap") or {}
    chapters = []
    for chapter in doc.get("chapterGroup") or []:
        chapter_out = {"title": str(chapter.get("title") or "详情"), "widgets": []}
        for widget_ref in chapter.get("widgets") or []:
            wid = str(widget_ref.get("id") or "")
            raw = widgets.get(wid) or {}
            tabs_by_id = raw.get("tabDataMap") or {}
            tab_labels = {str(t.get("tabId")): t for t in raw.get("tabList") or []}
            tabs = []
            for tab_id, tab in tabs_by_id.items():
                label = tab_labels.get(str(tab_id), {})
                audios = [a for a in (clean_audio(x) for x in tab.get("audioList") or []) if a]
                content_id = tab.get("content")
                tabs.append({
                    "id": str(tab_id),
                    "title": str(label.get("title") or widget_ref.get("title") or "详情"),
                    "icon": str(label.get("icon") or ""),
                    "blocks": rendered.get(content_id, []) if content_id else [],
                    "audios": audios,
                })
            table_list = [{"label": str(x.get("label") or ""), "value": str(x.get("value") or "")}
                          for x in raw.get("tableList") or [] if x.get("label") or x.get("value")]
            if tabs or table_list:
                chapter_out["widgets"].append({
                    "id": wid, "title": str(widget_ref.get("title") or "详情"),
                    "type": str(raw.get("type") or "common"),
                    "size": str(widget_ref.get("size") or "large"),
                    "facts": table_list, "tabs": tabs,
                })
        if chapter_out["widgets"]:
            chapters.append(chapter_out)
    brief = detail_item.get("brief") or item.get("brief") or {}
    return {
        "item_id": str(detail_item.get("itemId") or item.get("itemId") or ""),
        "name": str(detail_item.get("name") or item.get("name") or ""),
        "category": str(entry.get("subTypeName") or "干员"),
        "caption": render_inline(item.get("caption") or [], id2name),
        "cover": str(brief.get("cover") or "") if isinstance(brief, dict) else "",
        "illustration": str((doc.get("extraInfo") or {}).get("illustration") or ""),
        "chapters": chapters,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input")
    ap.add_argument("--out", default="output/operator_details.json")
    args = ap.parse_args()
    fname = args.input or sorted(glob.glob("endfield_wiki_full_*.json"))[-1]
    with open(fname, encoding="utf-8") as f:
        data = json.load(f)
    id2name = build_id2name(data["catalog"])
    operators = {}
    for entry in data["catalog"]:
        if entry.get("subTypeName") != "干员":
            continue
        operator = build_operator(entry, id2name)
        operators[operator["item_id"]] = operator
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"meta": {"source": data.get("meta", {}).get("source", ""),
                            "crawled_at": data.get("meta", {}).get("crawled_at", ""),
                            "count": len(operators)},
                   "operators": operators}, f, ensure_ascii=False, separators=(",", ":"))
    print(f"干员详情: {len(operators)} → {args.out}")


if __name__ == "__main__":
    main()
