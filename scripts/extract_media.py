# -*- coding: utf-8 -*-
"""
extract_media.py — 从 WIKI 全量 JSON 提取 图片/链接/引用 结构信息

背景：build_kb_all.py / recipe_extract.py 渲染块式富文本时，把以下结构信息丢弃了：
  - blockMap 里的 image 块（正文图片 URL）           → 只输出 "[图片]" 占位符
  - inline link 元素（外部链接 url+text）            → 直接丢弃
  - inline entry 元素里的 count（数量）与 showType    → 只取名称，数量/链接样式丢失
  - item.brief.cover（条目封面图）                   → 从未读取
  - document.extraInfo.illustration（条目配图）      → 从未读取

本脚本把这些信息原样提取为 output/item_media.json，
供前端展示物品图片 / 超链接 / 物品引用（点卡片跳转）。

用法:
    python scripts/extract_media.py                          # 默认读最新 endfield_wiki_full_*.json
    python scripts/extract_media.py --input xxx.json --out output/item_media.json

产物 output/item_media.json:
    {
      "meta": { ... },
      "items": {
        "1364": {
          "name": "重息壤",
          "category": "物品",
          "cover": "https://bbs.hycdn.cn/...",
          "illustration": "https://bbs.hycdn.cn/...",
          "images": ["https://...", ...],        # 正文图片（blockMap image 块）
          "links": [{"text": "...", "url": "..."}],
          "refs": [{"id": "771", "name": "息壤", "count": 10, "showType": "card-big"}, ...]
        }, ...
      }
    }
"""
import argparse
import glob
import json
import os
import sys

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")


def load_data(fname):
    """读取原始 WIKI 数据，供媒体链接和引用提取使用。"""
    with open(fname, encoding="utf-8") as f:
        return json.load(f)


def build_id2name(catalog):
    """条目 id（itemId/id/gameEntryId）→ 名称 映射，entry 引用靠它解析。"""
    id2name = {}
    for en in catalog:
        it = en.get("item") or {}
        for fid in (it.get("itemId"), it.get("id"), it.get("gameEntryId")):
            if fid is not None:
                id2name.setdefault(str(fid), it.get("name", ""))
        di = (en.get("detail") or {}).get("item")
        if di and di.get("itemId") is not None:
            id2name.setdefault(str(di.get("itemId")), di.get("name") or it.get("name", ""))
    return id2name


def item_of(en):
    """条目主 id（优先 detail.itemId，与配方库一致）。"""
    di = (en.get("detail") or {}).get("item") or {}
    it = en.get("item") or {}
    iid = di.get("itemId")
    if iid is None:
        iid = it.get("itemId")
    return str(iid) if iid is not None else str(it.get("id") or "")


def walk_inline(els, id2name, images, links, refs, seen_refs):
    """扫描一组 inline 元素，收集 image/link/entry。"""
    for e in els or []:
        k = e.get("kind")
        if k == "image":
            img = e.get("image") or {}
            url = (img.get("url") or "").strip()
            if url:
                images.append(url)
        elif k == "link":
            lk = e.get("link") or {}
            url = (lk.get("link") or "").strip()
            text = (lk.get("text") or "").strip()
            if url:
                links.append({"text": text, "url": url})
        elif k == "entry":
            ent = e.get("entry") or {}
            eid = str(ent.get("id") or "")
            if not eid:
                continue
            count = ent.get("count", "")
            try:
                count = float(count) if count not in ("", None) else 1.0
            except (TypeError, ValueError):
                count = 1.0
            key = (eid, count)
            if key in seen_refs:
                continue
            seen_refs.add(key)
            refs.append({
                "id": eid,
                "name": id2name.get(eid, ""),
                "count": count,
                "showType": ent.get("showType", ""),
            })


def extract_entry(en, id2name):
    """提取单个条目的封面、正文媒体、外链和条目引用。"""
    it = en.get("item") or {}
    di = (en.get("detail") or {}).get("item") or {}
    name = di.get("name") or it.get("name", "")
    category = en.get("subTypeName") or en.get("mainTypeName") or ""

    brief = di.get("brief") or it.get("brief") or {}
    cover = ""
    if isinstance(brief, dict):
        cover = (brief.get("cover") or "").strip()

    doc = di.get("document") or {}
    illustration = ""
    extra = doc.get("extraInfo") or {}
    if isinstance(extra, dict):
        illustration = (extra.get("illustration") or "").strip()

    images, links, refs = [], [], []
    seen_refs = set()
    docmap = doc.get("documentMap") or {}
    for _doc_k, doc_v in docmap.items():
        bm = doc_v.get("blockMap") or {}
        for _bk, bv in bm.items():
            kind = (bv or {}).get("kind")
            if kind == "image":
                img = bv.get("image") or {}
                url = (img.get("url") or "").strip()
                if url:
                    images.append(url)
            elif kind == "text":
                walk_inline(((bv.get("text") or {}).get("inlineElements") or []),
                            id2name, images, links, refs, seen_refs)
            elif kind == "table":
                tbl = bv.get("table") or {}
                cm = tbl.get("cellMap") or {}
                for _ck, cv in cm.items():
                    for cid in cv.get("childIds") or []:
                        cb = bm.get(cid) or {}
                        if cb.get("kind") == "image":
                            img = cb.get("image") or {}
                            url = (img.get("url") or "").strip()
                            if url:
                                images.append(url)
                        elif cb.get("kind") == "text":
                            walk_inline(((cb.get("text") or {}).get("inlineElements") or []),
                                        id2name, images, links, refs, seen_refs)

    def uniq(items, key):
        seen = set()
        out = []
        for it_ in items:
            k = key(it_)
            if k in seen:
                continue
            seen.add(k)
            out.append(it_)
        return out

    return {
        "item_id": item_of(en),
        "name": name,
        "category": category,
        "cover": cover,
        "illustration": illustration,
        "images": uniq(images, lambda x: x),
        "links": uniq(links, lambda x: x["url"]),
        "refs": refs,
    }


def main():
    """扫描全部条目并生成前端使用的 `output/item_media.json`。"""
    ap = argparse.ArgumentParser(description="提取 WIKI 图片/链接/引用结构信息")
    ap.add_argument("--input", help="全量 JSON；默认最新 endfield_wiki_full_*.json")
    ap.add_argument("--out", default="output/item_media.json")
    args = ap.parse_args()

    fname = args.input
    if not fname:
        cands = sorted(glob.glob("endfield_wiki_full_*.json"))
        if not cands:
            raise SystemExit("未找到输入文件，请用 --input 指定")
        fname = cands[-1]

    data = load_data(fname)
    catalog = data["catalog"]
    id2name = build_id2name(catalog)

    items = {}
    n_cover = n_illu = n_img = n_link = n_ref = 0
    for en in catalog:
        r = extract_entry(en, id2name)
        items[r["item_id"]] = r
        if r["cover"]:
            n_cover += 1
        if r["illustration"]:
            n_illu += 1
        if r["images"]:
            n_img += 1
        n_link += len(r["links"])
        n_ref += len(r["refs"])

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({
            "meta": {
                "source": data["meta"].get("source", ""),
                "crawled_at": data["meta"].get("crawled_at", ""),
                "total": len(items),
            },
            "items": items,
        }, f, ensure_ascii=False, indent=1)

    print(f"条目: {len(items)} | cover: {n_cover} | illustration: {n_illu} | 含正文图: {n_img}")
    print(f"链接总数: {n_link} | 引用总数: {n_ref}")
    print(f"输出: {args.out}")


if __name__ == "__main__":
    main()
