# -*- coding: utf-8 -*-
"""
recipe_extract.py — 从 WIKI 全量 JSON 结构化提取全部合成配方

用法:
    python scripts/recipe_extract.py                          # 默认读最新 endfield_wiki_full_*.json
    python scripts/recipe_extract.py --input xxx.json --out output/recipes.json

产物 output/recipes.json:
    {
      "recipes": [
        {
          "id": "m752-r0",
          "machine_id": "752", "machine": "天有洪炉",
          "inputs":  [{"item_id":"771","name":"息壤","count":10},
                      {"item_id":"1163","name":"壤晶废液","count":5}],
          "outputs": [{"item_id":"1364","name":"重息壤","count":1}],
          "duration": 1.0          # 单位时间/次，WIKI 无此数据，默认 1，可由时长表覆盖
        }, ...
      ]
    }

说明:
    - 配方数量来自表格单元格 entry.count（真实数据，非编造）
    - WIKI 数据不含生产时长；duration 默认 1.0，供规划算法使用
"""
import glob
import json
import os
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
    return id2name


def iter_tables(entry):
    """遍历一个条目的所有文档中的所有表格 block。yield (table_dict, blockMap)。"""
    di = (entry.get("detail") or {}).get("item") or {}
    doc = di.get("document") or {}
    docmap = doc.get("documentMap") or {}
    for doc_k, doc_v in docmap.items():
        bm = doc_v.get("blockMap") or {}
        for bk, bv in bm.items():
            if (bv or {}).get("kind") == "table":
                yield bv.get("table") or {}, bm


def cell_text_entries(tbl, bm, row_id, col_id):
    """渲染一个单元格：返回 (纯文本片段列表, entry 列表[(id,count)])。"""
    cm = tbl.get("cellMap") or {}
    cell = cm.get(f"{row_id}_{col_id}") or cm.get(f"{col_id}_{row_id}")
    texts, entries = [], []
    if not cell:
        return texts, entries
    for cid in cell.get("childIds") or []:
        cb = bm.get(cid)
        if not cb:
            continue
        els = (cb.get("text") or {}).get("inlineElements") or []
        for e in els:
            if e.get("kind") == "text":
                t = (e.get("text") or {}).get("text") or ""
                if t.strip():
                    texts.append(t)
            elif e.get("kind") == "entry":
                ent = e.get("entry") or {}
                iid = str(ent.get("id") or "")
                cnt = ent.get("count")
                try:
                    cnt = float(cnt) if cnt not in (None, "") else 1.0
                except ValueError:
                    cnt = 1.0
                entries.append((iid, cnt))
    return texts, entries

def parse_duration(s):
    """解析"2s"、"10s"、"1分钟"等时长文本，返回秒数。"""
    import re

    m = re.search(r"(\d+(?:\.\d+)?)\s*(s|秒|m|min|分钟|h|小时)?", s or "")
    if not m:
        return 1.0
    val = float(m.group(1))
    unit = m.group(2) or "s"
    if unit in ("m", "min", "分钟"):
        val *= 60
    elif unit in ("h", "小时"):
        val *= 3600
    return val


def parse_table(tbl, bm, id2name, cur_id, cur_name, cur_sub, device_ids, recipes, seen):
    """解析单个配方表格（通用列识别）。返回 (rows_ok, rows_skip)。

    支持两类配方表：
      A) 物品侧: 加工设备 | 原料需求 | 合成产物 [| 消耗时长]  （任何条目）
      B) 设备侧: 原料需求 | 制作产物 | 消耗时长  （仅设备条目 subType=5 才解析，设备=当前条目）

    说明：**不做激进清洗**——设备制造配方（产物是设备）、容器"盛装"配方、
    矿机配方、原木配方等全部保留，供合成树完整展示"怎么造"；
    自循环/循环等由合成树算法的剪枝规则处理（见 api_server.build_synthesis_tree）。

    单元格按 entry 读 item_id + count（数量）；时长列按文本解析秒数。
    """
    row_ids = tbl.get("rowIds") or []
    col_ids = tbl.get("columnIds") or []
    if not row_ids or not col_ids:
        return 0, 0

    # ---- 识别列角色 ----
    col_role = {}
    for rid in row_ids:
        row_texts = []
        for cid in col_ids:
            texts, _ = cell_text_entries(tbl, bm, rid, cid)
            row_texts.append("".join(texts))
        for ci, joined in enumerate(row_texts):
            if joined == "原料需求" or "原料需求" in joined:
                col_role.setdefault(ci, "input")
            elif "合成产物" in joined or "制作产物" in joined:
                col_role.setdefault(ci, "output")
            elif "消耗时长" in joined or "加工设备" in joined:
                if "消耗时长" in joined:
                    col_role.setdefault(ci, "duration")
                if "加工设备" in joined:
                    col_role.setdefault(ci, "machine")
        if any(r == "input" for r in col_role.values()) and any(
            r == "output" for r in col_role.values()
        ):
            break
    in_cols = [ci for ci, r in col_role.items() if r == "input"]
    out_cols = [ci for ci, r in col_role.items() if r == "output"]
    dur_cols = [ci for ci, r in col_role.items() if r == "duration"]
    mch_cols = [ci for ci, r in col_role.items() if r == "machine"]
    if not in_cols or not out_cols:
        return 0, 0

    rows_ok = rows_skip = 0
    last_machine = cur_id  # 设备侧表：设备 = 当前条目
    for rid in row_ids:
        # 跳过表头行
        joined = ["".join(cell_text_entries(tbl, bm, rid, cid)[0]) for cid in col_ids]
        if any("原料需求" in t or "合成产物" in t or "制作产物" in t for t in joined):
            continue
        # 原料 / 产物（entry -> item_id,count）
        inputs = []
        for ci in in_cols:
            _, es = cell_text_entries(tbl, bm, rid, col_ids[ci])
            inputs.extend((i, c) for i, c in es if i and c and c > 0)
        outputs = []
        for ci in out_cols:
            _, es = cell_text_entries(tbl, bm, rid, col_ids[ci])
            outputs.extend((i, c) for i, c in es if i and c and c > 0)
        if not inputs or not outputs:
            rows_skip += 1  # 模式行（基础模式/液体模式）或需求说明行
            continue
        # 设备列
        machine_id = None
        if mch_cols:
            _, es = cell_text_entries(tbl, bm, rid, col_ids[mch_cols[0]])
            machine_id = es[0][0] if es else None
            if machine_id:
                last_machine = machine_id
            else:
                machine_id = last_machine
        else:
            # 无设备列：仅设备条目（subType=5）的"相关配方"表才成立
            if cur_sub != "5":
                rows_skip += 1
                continue
            machine_id = cur_id or last_machine
        if not machine_id:
            rows_skip += 1
            continue
        # 时长
        duration = 1.0
        if dur_cols:
            texts, _ = cell_text_entries(tbl, bm, rid, col_ids[dur_cols[0]])
            duration = parse_duration("".join(texts))
        # 生成配方（不排除设备制造/矿机等——保留供合成树完整展示）
        key = (machine_id, tuple(sorted(inputs)), tuple(sorted(outputs)))
        if key in seen:
            # 同一配方已存在：若之前是默认时长而本次有真实时长，则更新
            old = seen[key]
            if abs(old.get("duration", 1.0) - 1.0) < 1e-9 and duration != 1.0:
                old["duration"] = duration
            rows_skip += 1
            continue
        recipe = {
            "id": f"m{machine_id}-r{len(recipes)}",
            "machine_id": machine_id,
            "machine": id2name.get(machine_id, machine_id) or cur_name,
            "inputs": [
                {"item_id": i, "name": id2name.get(i, i), "count": c}
                for i, c in sorted(inputs)
            ],
            "outputs": [
                {"item_id": i, "name": id2name.get(i, i), "count": c}
                for i, c in sorted(outputs)
            ],
            "duration": duration,
        }
        seen[key] = recipe
        recipes.append(recipe)
        rows_ok += 1
    return rows_ok, rows_skip



def main():
    import argparse

    ap = argparse.ArgumentParser(description="从 WIKI 全量 JSON 提取全部配方")
    ap.add_argument("--input", help="全量 JSON；默认最新 endfield_wiki_full_*.json")
    ap.add_argument("--out", default="output/recipes.json", help="输出配方库 JSON")
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

    recipes, seen = [], {}
    stat = {"ok": 0, "skip": 0, "tables": 0}
    device_ids = {str(en.get("item", {}).get("itemId")) for en in catalog if str(en.get("subTypeId")) == "5"}
    for en in catalog:
        it = en.get("item") or {}
        cur_id = str(it.get("itemId") or "")
        cur_name = it.get("name", "")
        cur_sub = str(en.get("subTypeId") or "")
        for tbl, bm in iter_tables(en):
            stat["tables"] += 1
            a, b = parse_table(tbl, bm, id2name, cur_id, cur_name, cur_sub, device_ids, recipes, seen)
            stat["ok"] += a
            stat["skip"] += b

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    # ---- 不做激进清洗：设备制造/容器盛装/矿机/原木等配方全部保留，
    #     由合成树算法的剪枝规则（自循环排除/循环剪枝/种子叶子）保证树干净 ----
    # ---- 后处理：补全缺失名称 ----
    for r in recipes:
        if not r.get("machine"):
            r["machine"] = id2name.get(r["machine_id"], r["machine_id"])
        for x in r["inputs"] + r["outputs"]:
            x["name"] = (x.get("name") or "").strip() or id2name.get(x["item_id"], x["item_id"])
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump({"recipes": recipes}, f, ensure_ascii=False, indent=1)

    machines = sorted({r["machine_id"] for r in recipes})
    items = sorted({x["item_id"] for r in recipes for x in r["inputs"] + r["outputs"]})
    print(f"解析表格: {stat['tables']} | 配方: {len(recipes)} | 跳过行: {stat['skip']}")
    print(f"涉及设备: {len(machines)} 种 | 涉及物品: {len(items)} 种")
    print(f"输出: {args.out}")


if __name__ == "__main__":
    main()
