# -*- coding: utf-8 -*-
"""
build_kb_all.py — 把 WIKI 全量 JSON 按子分类提取为知识库（jsonl + md），供 RAG 使用

与 build_kb.py 相同方式解析块式富文本，但遍历全部子分类，每个分类输出：
  endfield_kb/{分类}.jsonl   （RAG 输入，含 item_id/name/sections/full_text）
  endfield_kb/{分类}.md      （人类可读）
  endfield_kb/_catalog.json  （全部分类清单）

用法:
  python scripts/build_kb_all.py
  python scripts/build_kb_all.py --input endfield_wiki_full_xxx.json --out-dir endfield_kb
"""
import argparse
import glob
import json
import os
import re
import sys

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")


def load_data(fname):
    with open(fname, encoding="utf-8") as f:
        return json.load(f)


def build_id2name(catalog):
    id2name = {}
    for en in catalog:
        it = en.get("item") or {}
        for fid in (it.get("itemId"), it.get("id"), it.get("gameEntryId")):
            if fid is not None:
                id2name.setdefault(str(fid), it.get("name", ""))
        d = en.get("detail")
        if d and d.get("item"):
            di = d["item"]
            id2name.setdefault(str(di.get("itemId")), di.get("name") or it.get("name", ""))
    return id2name


def render_inline(els, id2name):
    """渲染 inline 元素序列。

    规则：
      - text 元素直接拼接（是同一句话的分段）
      - entry（物品引用/超链接卡片）渲染为「名称×数量」，前面补空格避免与前后文字粘连
      - link（外部链接）渲染为链接文本（保留信息）
      - image 渲染为 [图片] 标记
    """
    out = ""
    for el in els or []:
        k = el.get("kind")
        t = ""
        if k == "text":
            t = (el.get("text") or {}).get("text") or ""
        elif k == "entry":
            ent = el.get("entry") or {}
            eid = str(ent.get("id") or "")
            nm = (id2name.get(eid, f"[物品:{eid}]") if eid else "").strip()
            if nm:
                cnt = ent.get("count")
                if cnt not in (None, "", "0"):
                    nm = f"{nm}×{cnt}"
                t = nm
        elif k == "link":
            lk = el.get("link") or {}
            t = (lk.get("text") or "").strip() or (lk.get("link") or "").strip()
        elif k == "image":
            t = "[图片]"
        if not t:
            continue
        if out and k != "text" and not out[-1].isspace():
            out += " "
        out += t
    return out.strip()


def render_block(bv, blockmap, id2name, depth=0):
    kind = bv.get("kind")
    lines = []
    if kind == "text":
        txt = render_inline((bv.get("text") or {}).get("inlineElements") or [], id2name)
        if txt.strip():
            lines.append(("  " * depth) + txt.strip())
    elif kind == "list":
        lst = bv.get("list") or {}
        item_ids = lst.get("itemIds") or []
        item_map = lst.get("itemMap") or {}
        bullet = "- " if lst.get("kind") == "unordered" else "1. "
        for iid in item_ids:
            node = item_map.get(iid, {})
            child_ids = node.get("childIds") or []
            sub_lines = []
            for cid in child_ids:
                cb = blockmap.get(cid)
                if cb:
                    sub_lines.extend(render_block(cb, blockmap, id2name, depth + 1))
            if sub_lines:
                lines.append(("  " * depth) + bullet + sub_lines[0].strip())
                for sl in sub_lines[1:]:
                    lines.append(("  " * (depth + 1)) + sl.strip())
            else:
                lines.append(("  " * depth) + bullet)
    elif kind == "table":
        tbl = bv.get("table") or {}
        row_ids = tbl.get("rowIds") or []
        col_ids = tbl.get("columnIds") or []
        cell_map = tbl.get("cellMap") or {}
        if row_ids and col_ids:
            lines.append("[表格]")
            for rid in row_ids:
                cells = []
                for cid in col_ids:
                    cell = cell_map.get(f"{rid}_{cid}") or cell_map.get(f"{cid}_{rid}")
                    if not cell:
                        cells.append("")
                        continue
                    sub = []
                    for x in (cell.get("childIds") or []):
                        cb = blockmap.get(x)
                        if cb:
                            sub.extend(render_block(cb, blockmap, id2name))
                    cells.append(" / ".join(s.strip() for s in sub if s and s.strip()))
                lines.append(" | ".join(cells))
    elif kind == "image":
        img = bv.get("image") or {}
        url = (img.get("url") or "").strip()
        lines.append("[图片]" + (f"({url})" if url else ""))
    return lines


def render_inline_struct(els, id2name):
    """渲染 inline 元素为结构化数组（供前端渲染图片/表格/物品卡片）。

    元素类型: text / entry(物品引用) / link(外链) / img
    """
    out = []
    for el in els or []:
        k = el.get("kind")
        if k == "text":
            t = (el.get("text") or {}).get("text") or ""
            if t:
                item = {"t": "text", "x": t}
                if el.get("bold"):
                    item["b"] = True
                if el.get("italic"):
                    item["i"] = True
                if el.get("color"):
                    item["color"] = str(el["color"])
                out.append(item)
        elif k == "entry":
            ent = el.get("entry") or {}
            eid = str(ent.get("id") or "")
            nm = (id2name.get(eid, f"[物品:{eid}]") if eid else "").strip()
            if not nm:
                continue
            cnt = ent.get("count", "")
            try:
                cnt = float(cnt) if cnt not in ("", None) else 0
            except (TypeError, ValueError):
                cnt = 0
            out.append({"t": "entry", "x": nm, "id": eid, "c": cnt})
        elif k == "link":
            lk = el.get("link") or {}
            t = (lk.get("text") or "").strip() or (lk.get("link") or "").strip()
            if t:
                out.append({"t": "link", "x": t, "u": (lk.get("link") or "").strip()})
        elif k == "image":
            u = ((el.get("image") or {}).get("url") or "").strip()
            if u:
                out.append({"t": "img", "u": u})
    return out


def render_block_struct(bv, blockmap, id2name):
    """渲染单个块为结构化对象列表（text/image/list/table）。"""
    kind = bv.get("kind")
    blocks = []
    if kind == "text":
        els = render_inline_struct((bv.get("text") or {}).get("inlineElements") or [], id2name)
        if els:
            blocks.append({"t": "para", "c": els,
                           "kind": (bv.get("text") or {}).get("kind", "body"),
                           "align": bv.get("align", "left")})
    elif kind == "image":
        u = ((bv.get("image") or {}).get("url") or "").strip()
        if u:
            blocks.append({"t": "img", "u": u,
                           "alt": ((bv.get("image") or {}).get("description") or "").strip()})
    elif kind == "horizontalLine":
        blocks.append({"t": "hr"})
    elif kind == "externalVideo":
        video = bv.get("externalVideo") or {}
        if video.get("id"):
            blocks.append({"t": "video", "id": str(video["id"]),
                           "kind": str(video.get("kind") or "skland")})
    elif kind == "list":
        lst = bv.get("list") or {}
        for iid in lst.get("itemIds") or []:
            node = (lst.get("itemMap") or {}).get(iid, {})
            for cid in node.get("childIds") or []:
                cb = blockmap.get(cid)
                if cb:
                    blocks.extend(render_block_struct(cb, blockmap, id2name))
    elif kind == "table":
        tbl = bv.get("table") or {}
        row_ids = tbl.get("rowIds") or []
        col_ids = tbl.get("columnIds") or []
        cm = tbl.get("cellMap") or {}
        if row_ids and col_ids:
            rows = []
            for rid in row_ids:
                cells = []
                for cid in col_ids:
                    cell = cm.get(f"{rid}_{cid}") or cm.get(f"{cid}_{rid}")
                    cell_els = []
                    if cell:
                        for x in cell.get("childIds") or []:
                            cb = blockmap.get(x)
                            if not cb:
                                continue
                            if cb.get("kind") == "image":
                                u = ((cb.get("image") or {}).get("url") or "").strip()
                                if u:
                                    cell_els.append({"t": "img", "u": u})
                            else:
                                cell_els.extend(
                                    render_inline_struct((cb.get("text") or {}).get("inlineElements") or [], id2name)
                                )
                    cells.append(cell_els)
                rows.append(cells)
            if rows:
                blocks.append({"t": "table", "r": rows})
    return blocks


def render_document_struct(doc_entry, id2name):
    blockmap = doc_entry.get("blockMap") or {}
    out = []
    for bid in doc_entry.get("blockIds") or []:
        bv = blockmap.get(bid)
        if bv:
            out.extend(render_block_struct(bv, blockmap, id2name))
    return out


def render_document(doc_entry, id2name):
    blockmap = doc_entry.get("blockMap") or {}
    out = []
    for bid in doc_entry.get("blockIds") or []:
        bv = blockmap.get(bid)
        if bv:
            out.extend(render_block(bv, blockmap, id2name, 0))
    return "\n".join(out)


def extract_entry(en, id2name):
    """把 catalog 单条渲染成 {item_id,name,caption,sections,documents}。"""
    it = en.get("item") or {}
    detail = en.get("detail") or {}
    di = detail.get("item") or {}
    doc = di.get("document") or {}
    docmap = doc.get("documentMap") or {}
    chapter_group = doc.get("chapterGroup") or []
    widget_map = doc.get("widgetCommonMap") or {}

    name = it.get("name") or di.get("name") or ""
    item_id = str(it.get("itemId") or di.get("itemId") or "")

    rendered = {dk: render_document(dv, id2name) for dk, dv in docmap.items()}
    rendered_struct = {dk: render_document_struct(dv, id2name) for dk, dv in docmap.items()}

    sections = {}
    sections_struct = {}
    for ch in chapter_group:
        ch_title = ch.get("title", "")
        ch_data = {}
        ch_data_struct = {}
        for w in ch.get("widgets") or []:
            w_title = w.get("title", "")
            w_id = w.get("id", "")
            w_info = widget_map.get(w_id) or {}
            content_key = ((w_info.get("tabDataMap") or {}).get("default") or {}).get("content")
            ch_data[w_title] = rendered.get(content_key, "") if content_key else ""
            if content_key:
                s = rendered_struct.get(content_key, [])
                if s:
                    ch_data_struct[w_title] = s
        if ch_data:
            sections[ch_title] = ch_data
        if ch_data_struct:
            sections_struct[ch_title] = ch_data_struct

    return {
        "item_id": item_id,
        "name": name,
        "lang": it.get("lang") or di.get("lang") or "",
        "caption": render_inline(it.get("caption") or [], id2name),
        "brief_description": (it.get("brief") or {}).get("description"),
        "sections": sections,
        "sections_struct": sections_struct,
        "documents": rendered,
    }


def build_full_text(dev):
    section_text = {}
    for ch, ws in (dev["sections"] or {}).items():
        for wt, text in ws.items():
            section_text[wt] = (text or "").strip()
    parts = [f"名称: {dev['name']}"]
    if dev.get("caption"):
        parts.append(f"描述: {dev['caption']}")
    for wt, txt in section_text.items():
        if txt:
            parts.append(f"{wt}: {txt}")
    for dk, txt in (dev["documents"] or {}).items():
        in_section = any(txt == st for ws in (dev["sections"] or {}).values() for st in ws.values())
        if txt.strip() and not in_section:
            parts.append(f"其他内容: {txt.strip()}")
    return "\n".join(p for p in parts if p)


def main():
    ap = argparse.ArgumentParser(description="按子分类提取 WIKI 全量数据为知识库（jsonl+md）")
    ap.add_argument("--input", help="全量 JSON；默认最新 endfield_wiki_full_*.json")
    ap.add_argument("--out-dir", default="endfield_kb", help="输出目录（默认 endfield_kb/）")
    args = ap.parse_args()

    fname = args.input or sorted(glob.glob("endfield_wiki_full_*.json"))[-1]
    data = load_data(fname)
    catalog = data["catalog"]
    id2name = build_id2name(catalog)

    # ---- 按 subTypeId 分组 ----
    groups = {}
    for en in catalog:
        sid = str(en.get("subTypeId"))
        g = groups.setdefault(sid, {
            "subTypeName": en.get("subTypeName") or f"分类{sid}",
            "mainTypeName": en.get("mainTypeName") or "",
            "entries": [],
        })
        g["entries"].append(en)

    os.makedirs(args.out_dir, exist_ok=True)

    # ---- 分类清单 ----
    catalog_list = []
    for sid in sorted(groups, key=lambda x: int(x) if x.isdigit() else 0):
        g = groups[sid]
        catalog_list.append({
            "subTypeId": sid,
            "subTypeName": g["subTypeName"],
            "mainTypeName": g["mainTypeName"],
            "entry_count": len(g["entries"]),
        })
    with open(os.path.join(args.out_dir, "_catalog.json"), "w", encoding="utf-8") as f:
        json.dump({
            "source": data["meta"].get("source", ""),
            "crawled_at": data["meta"].get("crawled_at", ""),
            "total": len(catalog),
            "categories": catalog_list,
        }, f, ensure_ascii=False, indent=1)

    print(f"全量 {len(catalog)} 条 / {len(groups)} 个分类\n")

    # ---- 逐分类提取 ----
    total_entries = 0
    for sid in sorted(groups, key=lambda x: int(x) if x.isdigit() else 0):
        g = groups[sid]
        stem = re.sub(r'[\\/:*?"<>|\s]+', "_", f"{g['mainTypeName']}_{g['subTypeName']}")
        jsonl_path = os.path.join(args.out_dir, f"{stem}.jsonl")
        md_path = os.path.join(args.out_dir, f"{stem}.md")

        jsonl_lines, md_chunks = [], []
        for i, en in enumerate(g["entries"]):
            dev = extract_entry(en, id2name)
            full_text = build_full_text(dev)
            jsonl_lines.append(json.dumps({
                "item_id": dev["item_id"],
                "name": dev["name"],
                "category": g["subTypeName"],
                "sections": {wt: txt.strip()
                             for ws in (dev["sections"] or {}).values()
                             for wt, txt in ws.items() if txt and txt.strip()},
                "sections_struct": {wt: s
                                    for ws in (dev["sections_struct"] or {}).values()
                                    for wt, s in ws.items()},
                "full_text": full_text,
            }, ensure_ascii=False))

            md_chunks.append(f"## {dev['name']} (ID: {dev['item_id']})\n")
            if dev.get("caption"):
                md_chunks.append(f"**描述**：{dev['caption']}\n")
            for ch, ws in (dev["sections"] or {}).items():
                md_chunks.append(f"### {ch}\n")
                for wt, text in ws.items():
                    if text and text.strip():
                        md_chunks.append(f"**{wt}**：\n\n{text.strip()}\n")
            md_chunks.append("---\n")

        with open(jsonl_path, "w", encoding="utf-8") as f:
            f.write("\n".join(jsonl_lines) + ("\n" if jsonl_lines else ""))
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(f"# 明日方舟：终末地 WIKI · {g['subTypeName']} 知识库\n\n")
            f.write(f"> 数据来源：{data['meta'].get('source', '')}（抓取 {data['meta'].get('crawled_at', '')}）\n\n")
            f.write(f"> 共 {len(g['entries'])} 个条目\n\n")
            f.writelines(md_chunks)

        total_entries += len(g["entries"])
        print(f"  [{sid}] {g['subTypeName']}（{g['mainTypeName']}）: "
              f"{len(g['entries'])} 条 → {os.path.relpath(jsonl_path)}")

    print(f"\n完成: 共 {total_entries} 条 → {os.path.abspath(args.out_dir)}/")


if __name__ == "__main__":
    main()
