# -*- coding: utf-8 -*-
"""
recipe_index.py — 配方索引通用工具（从 recipes.json 构建物品索引、按名查物品 ID）

被 api_server.py（合成树/问答）与 eval_rag.py 复用，不依赖任何规划算法。
"""
import json


def load_recipes(path="output/recipes.json"):
    """读取 recipes.json，返回配方列表。"""
    with open(path, encoding="utf-8") as f:
        return (json.load(f) or {}).get("recipes", [])


def build_item_index(recipes):
    """item_id -> {name, produce_by:[配方], consume_by:[配方]}。"""
    idx = {}
    for r in recipes:
        for x in r["inputs"]:
            e = idx.setdefault(x["item_id"], {"name": x["name"], "produce_by": [], "consume_by": []})
            e["consume_by"].append(r)
            e["name"] = x["name"]
        for x in r["outputs"]:
            e = idx.setdefault(x["item_id"], {"name": x["name"], "produce_by": [], "consume_by": []})
            e["produce_by"].append(r)
            e["name"] = x["name"]
    return idx


def find_item_ids_by_name(recipes, name):
    """按名称匹配物品 ID：优先精确，其次名称子串。"""
    name = name.strip()
    exact = {x["item_id"] for r in recipes for x in r["inputs"] + r["outputs"]
             if x["name"].strip() == name}
    if exact:
        return sorted(exact)
    return sorted({x["item_id"] for r in recipes for x in r["inputs"] + r["outputs"]
                   if name in x["name"]})
