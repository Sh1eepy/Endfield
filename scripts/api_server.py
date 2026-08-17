# -*- coding: utf-8 -*-
"""
api_server.py — 终末地配方合成树 API（FastAPI）

供前端网页调用：
  GET  /api/health                健康检查
  GET  /api/synthesis?item=重息壤   合成树（物品树 / 设备配方卡 / 无配方→知识库信息）
  GET  /api/names                 全部名称（前端模糊搜索联想）

启动:
  python -m uvicorn scripts.api_server:app --host 0.0.0.0 --port 8000

调用示例:
  curl "http://127.0.0.1:8000/api/synthesis?item=重息壤"
  curl http://127.0.0.1:8000/api/names
"""
import json
import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "scripts"))
if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")


def _load_env():
    """加载项目根 .env（LLM_API_KEY 等），不覆盖已存在的环境变量。"""
    env_path = os.path.join(ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip())


_load_env()

from recipe_index import load_recipes, build_item_index, find_item_ids_by_name  # noqa: E402

app = FastAPI(title="终末地配方合成树", version="1.0.0")

# 展示阶段：放开跨域，便于本地静态页直连
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "endfield-wiki-agent"}


# ===================== WIKI 合成树 =====================

# 基础资源：免费资源（区域外供给）——清水/惰气/息壤气
BASE_FREE = {"清水", "惰气", "息壤气"}


def _is_base(iid, item_index):
    """叶子判定：基础资源 = 免费资源 / 无产出配方（矿物等） / 种子类（种植循环终止点）。"""
    name = item_index[iid]["name"].strip()
    if name in BASE_FREE:
        return True
    producers = item_index[iid].get("produce_by", [])
    if not producers:
        return True                     # 无产出配方 → 矿物等基础资源
    if "种子" in name:
        return True                     # 种子类：种植循环终止点（芽针种子/锦草种子…）
    return False


def _lookup_item_kb(name):
    """从 endfield_kb/*.jsonl 按名称精确匹配条目（无配方物品的回退信息来源）。"""
    import glob as _glob

    key = name.strip()
    for f in _glob.glob(os.path.join(ROOT, "endfield_kb", "*.jsonl")):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                if d.get("name") == key:
                    return d
    return None


_ITEM_MEDIA = None


def _load_item_media():
    """加载 output/item_media.json（封面图/引用/链接），首次加载后缓存。"""
    global _ITEM_MEDIA
    if _ITEM_MEDIA is None:
        try:
            with open(os.path.join(ROOT, "output", "item_media.json"), encoding="utf-8") as f:
                _ITEM_MEDIA = json.load(f).get("items") or {}
        except (OSError, ValueError):
            _ITEM_MEDIA = {}
    return _ITEM_MEDIA


def _media_cover(media, iid):
    """取某 item_id 的封面图 URL（无则空串）。"""
    m = (media or {}).get(str(iid)) or {}
    return (m.get("cover") or "").strip()


def _refs_summary(refs, limit=10):
    """物品引用摘要：过滤无名称条目，截取前 limit 条供前端做可点击卡片。"""
    out = []
    for r in refs or []:
        name = (r.get("name") or "").strip()
        if not name:
            continue
        cnt = r.get("count")
        try:
            cnt = int(cnt) if float(cnt).is_integer() else float(cnt)
        except (TypeError, ValueError):
            cnt = None
        out.append({"name": name, "count": cnt, "showType": r.get("showType", "")})
        if len(out) >= limit:
            break
    return out


def _pick_producers(producers, item_index):
    """配方选择：排除自循环，按 (输入数, -输入中基础原料数) 排序，最多 2 个。"""
    scored = []
    for r in producers:
        in_ids = {x["item_id"] for x in r["inputs"]}
        if any(x["item_id"] in in_ids for x in r["outputs"]):
            continue                      # 自循环配方（输出含输入）跳过
        n_in = len(r["inputs"])
        n_base = sum(1 for x in r["inputs"] if _is_base(x["item_id"], item_index))
        scored.append((n_in, -n_base, r))
    scored.sort(key=lambda t: (t[0], t[1]))
    return [t[2] for t in scored[:2]]


def build_synthesis_tree(item_id, recipes, item_index, max_depth=10, media=None):
    """从目标物品递归展开合成树。

    规则：
      - 叶子 = 基础资源（免费资源 / 无产出配方矿物 / 种植机·采种机产出的植物类）
      - 每个物品最多展开 2 个配方（排除自循环，优先输入少/含基础原料多）
      - 循环（出现在当前路径）或超深的**分支直接剪掉**，不显示非基础叶子
    """
    def expand(iid, depth, path):
        if depth > max_depth or iid in path:
            return None                     # 剪枝：无法收敛到基础资源
        node = {"name": item_index[iid]["name"].strip(), "item_id": iid, "depth": depth}
        cover = _media_cover(media, iid)
        if cover:
            node["cover"] = cover
        if _is_base(iid, item_index):
            node["leaf"] = True
            return node
        producers = _pick_producers(item_index[iid].get("produce_by", []), item_index)
        if not producers:
            return None
        node["recipes"] = []
        for r in producers:
            rc = {"machine": r["machine"],
                  "machine_id": str(r.get("machine_id") or ""),
                  "duration": r.get("duration", 1.0),
                  "inputs": []}
            ok = True
            for x in r["inputs"]:
                child = expand(x["item_id"], depth + 1, path | {iid})
                if child is None:
                    ok = False             # 该输入无法收敛到基础资源 → 剪掉整个配方
                    break
                child["count"] = x["count"]
                rc["inputs"].append(child)
            if ok:
                node["recipes"].append(rc)
        if not node["recipes"]:
            return None                     # 所有配方都剪掉 → 该物品不显示
        return node

    return expand(item_id, 0, set()), None


def _kb_summary(kb):
    """知识库条目摘要（供前端显示无配方物品的信息）。

    sections_struct: 结构化块（text/table/image/entry），前端渲染成真表格/真图片。
    """
    sections = {}
    for k, v in (kb.get("sections") or {}).items():
        if v and str(v).strip():
            sections[str(k)] = str(v)[:300]
    ss = (kb.get("sections_struct") or {}) or {}
    return {"name": kb.get("name"), "category": kb.get("category"),
            "item_id": str(kb.get("item_id") or ""),
            "sections": sections,
            "sections_struct": {str(k): v for k, v in ss.items() if v},
            "full_text": (kb.get("full_text") or "")[:800]}


@app.get("/api/synthesis")
def synthesis(item: str, max_depth: int = 10):
    if not item or not item.strip():
        return {"ok": False, "error": "请输入物品或设备名称"}
    if max_depth < 0:
        return {"ok": False, "error": "max_depth 不能小于 0"}
    recipes = load_recipes(os.path.join(ROOT, "output", "recipes.json"))
    item_index = build_item_index(recipes)
    media = _load_item_media()
    tids = find_item_ids_by_name(recipes, item)
    if len(tids) > 1:
        # 名称匹配多个物品（如"灼铜"→气态灼铜/灼铜块/...）→ 返回候选列表让前端选择
        cands = sorted({item_index[i]["name"].strip() for i in tids})
        return {"ok": True, "ambiguous": True, "item": item.strip(), "candidates": cands}
    if len(tids) == 1:
        tid = tids[0]
        tree, _ = build_synthesis_tree(tid, recipes, item_index, max_depth, media)
        if tree and tree.get("recipes"):
            return {"ok": True, "item": item_index[tid]["name"].strip(), "tree": tree,
                    "cover": _media_cover(media, tid),
                    "refs": _refs_summary((media or {}).get(str(tid), {}).get("refs"))}
        # 无配方（非流水线物品）→ 回退知识库返回物品本身信息
        kb = _lookup_item_kb(item)
        if kb:
            return {"ok": True, "item": item_index[tid]["name"].strip(),
                    "no_recipe": True, "kb": _kb_summary(kb),
                    "cover": _media_cover(media, tid),
                    "refs": _refs_summary((media or {}).get(str(tid), {}).get("refs"))}
        return {"ok": False, "error": f"物品 '{item}' 无配方且知识库未收录"}

    # 不是物品 → 尝试设备名：返回该设备能造的配方列表
    machine_ids = {}
    for r in recipes:
        machine_ids.setdefault(str(r.get("machine_id") or ""), r["machine"])
    by_name = {m.strip(): mid for mid, m in machine_ids.items()}
    key = item.strip()
    if key in by_name:
        mid = by_name[key]
        dev_recipes = [r for r in recipes if str(r.get("machine_id") or "") == mid]
        tree = {
            "name": machine_ids[mid], "item_id": mid, "depth": 0,
            "kind": "device",
            "recipes": [{
                "machine": r["machine"], "duration": r.get("duration", 1.0),
                "inputs": [{"name": item_index.get(x["item_id"], {}).get("name", x["name"]),
                            "count": x["count"]} for x in r["inputs"]],
                "outputs": [{"name": item_index.get(x["item_id"], {}).get("name", x["name"]),
                             "count": x["count"]} for x in r["outputs"]],
            } for r in dev_recipes],
        }
        return {"ok": True, "item": key, "tree": tree,
                "cover": _media_cover(media, mid),
                "refs": _refs_summary((media or {}).get(str(mid), {}).get("refs"))}

    # 物品/设备都没匹配到 → 回退知识库返回物品本身信息
    kb = _lookup_item_kb(item)
    if kb:
        kid = str(kb.get("item_id") or "")
        return {"ok": True, "item": key, "no_recipe": True, "kb": _kb_summary(kb),
                "cover": _media_cover(media, kid),
                "refs": _refs_summary((media or {}).get(kid, {}).get("refs"))}
    return {"ok": False, "error": f"物品/设备 '{item}' 匹配 0 个，请用精确名称"}

# ===================== 名称建议（前端模糊搜索）=====================

_NAMES_CACHE = None


def _load_all_names():
    """收集全部名称：配方物品 + 设备 + 知识库条目（供搜索联想）。"""
    result = set()
    recipes = load_recipes(os.path.join(ROOT, "output", "recipes.json"))
    item_index = build_item_index(recipes)
    for e in item_index.values():
        result.add(e["name"].strip())
    for r in recipes:
        if r.get("machine"):
            result.add(r["machine"].strip())
    import glob as _glob

    for f in _glob.glob(os.path.join(ROOT, "endfield_kb", "*.jsonl")):
        with open(f, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                n = d.get("name")
                if n and n.strip():
                    result.add(n.strip())
    return sorted(result)


@app.get("/api/names")
def names():
    """返回全部名称列表（首次加载后缓存），供前端本地模糊过滤。"""
    global _NAMES_CACHE
    if _NAMES_CACHE is None:
        _NAMES_CACHE = _load_all_names()
    return {"names": _NAMES_CACHE, "count": len(_NAMES_CACHE)}


# ===================== RAG 问答（阶段 5）=====================

from pydantic import BaseModel as _BaseModel  # noqa: E402


class AskRequest(_BaseModel):
    query: str
    top_k: int = 5
    gen_answer: bool = True


@app.post("/api/ask")
def ask_endpoint(req: AskRequest):
    """RAG 问答入口：意图识别 → 路由（配方直查/RAG检索）→ LLM 生成带引用回答。

    请求体: {"query": "重息壤是什么", "top_k": 5, "gen_answer": true}
    """
    from rag_ask import ask
    return ask(req.query, top_k=req.top_k, gen_answer_=req.gen_answer)


# ---- 静态前端（web/ 目录），放在最后挂载以免覆盖 /api/* ----
web_dir = os.path.join(ROOT, "web")
if os.path.isdir(web_dir):
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
