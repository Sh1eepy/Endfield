# -*- coding: utf-8 -*-
"""知识问答主流程。

顺序是“意图识别 → 确定性直查/图检索/RAG → 可选 LLM 生成”。配方、枚举和明确关系优先使用
结构化数据；图或直查没有证据时再回退文本检索。这个模块负责组织步骤，不修改索引和知识图谱。

用法:
    from rag_ask import ask
    result = ask("重息壤怎么合成")
    result = ask("重息壤是什么", gen_answer_=True)

CLI:
    python scripts/rag_ask.py "重息壤是什么" --gen
"""
import argparse
import json
import os
import re
import sys

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from intent_router import classify_query  # noqa: E402
from llm_client import llm  # noqa: E402

# 惰性加载的单例（避免每次 ask 都重载索引）
_retriever = None
_recipes = None
_item_index = None
_kb_names = None      # 知识库条目名 → 条目摘要缓存（实体抽取用）


def _get_retriever():
    global _retriever
    if _retriever is None:
        from rag_search import RAGRetriever
        _retriever = RAGRetriever(os.path.join(ROOT, "output", "rag"))
    return _retriever


def _get_recipes():
    global _recipes, _item_index
    if _recipes is None:
        from recipe_index import load_recipes, build_item_index
        _recipes = load_recipes(os.path.join(ROOT, "output", "recipes.json"))
        _item_index = build_item_index(_recipes)
    return _recipes, _item_index


def _get_kb_names():
    """知识库条目名集合（干员/武器/装备/任务/物品…），供实体抽取。
    返回 dict: 条目名 → {"category": ..., "full_text": ...}
    """
    global _kb_names
    if _kb_names is None:
        import glob as _glob
        _kb_names = {}
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
                    n = (d.get("name") or "").strip()
                    if n and n not in _kb_names:
                        _kb_names[n] = {"category": d.get("category", ""),
                                        "full_text": (d.get("full_text") or "")}
    return _kb_names


# ===================== 结构化直查 =====================

def extract_item_name(query):
    """从自由文本查询中抽取配方/设备名：遍历配方库全部名称，取查询中包含的最长匹配。

    "重息壤怎么合成" → "重息壤"
    "天有洪炉" → "天有洪炉"（设备）
    返回 (name, kind) 或 (None, None)。kind: item / device。
    """
    recipes, item_index = _get_recipes()
    q = query.strip()
    if not q:
        return None, None
    # 收集候选：物品名 + 设备名
    cands = {e["name"].strip() for e in item_index.values() if e["name"].strip()}
    for r in recipes:
        if r.get("machine"):
            cands.add(r["machine"].strip())
    # 只保留出现在查询中的名称，按长度降序取最长
    hits = sorted([c for c in cands if c and c in q], key=len, reverse=True)
    if not hits:
        return None, None
    best = hits[0]
    machines = {r["machine"].strip() for r in recipes if r.get("machine")}
    kind = "device" if best in machines else "item"
    return best, kind


def extract_kb_entity(query):
    """从知识库条目名中抽取实体（干员/武器/装备/任务等，不在配方库的）。

    "诀从一级升到满级要多少材料" → "诀"（干员条目）
    "佩丽卡怎么培养" → "佩丽卡"
    返回 (name, kb_info) 或 (None, None)。kb_info: {"category", "full_text"}。
    注意：优先精确名（排除"诀的信物/头像·诀"这类衍生条目），次选最长包含。
    """
    kb = _get_kb_names()
    q = query.strip()
    if not q:
        return None, None
    # 精确名优先：查询里完整出现某个条目名
    exact = sorted([n for n in kb if n and n in q], key=len, reverse=True)
    if not exact:
        return None, None
    best = exact[0]
    # 衍生条目（带 ·/·/：/（）等修饰）优先级低：如查询含"诀"也含"诀的信物"，
    # 应取"诀"（干员主条目）而非"诀的信物"。取最短的精确命中作为主实体。
    cands = [n for n in exact if n == best or len(n) == min(len(x) for x in exact)]
    main = min(cands, key=len)
    return main, kb.get(main)


def kb_direct_hits(query, top_n=3):
    """实体定位：从知识库抽实体，返回该实体所在条目（含全文）的检索命中列表。

    用于"诀从一级升到满级要多少材料"这类——实体明确、但被问题其他词干扰
    导致向量检索排不前的场景：直接定位条目全文当上下文，绕开检索噪声。
    返回 [{meta, text}] 或 []。
    """
    name, info = extract_kb_entity(query)
    if not name or not info:
        return []
    text = info.get("full_text") or ""
    if not text:
        return []
    return [{
        "meta": {"name": name, "category": info.get("category", ""), "item_id": "", "chunk_index": 0},
        "text": text, "score": 1.0, "vector_sim": 1.0, "bm25_score": 0.0,
        "_direct": True,
    }]


# ===================== ③ mention 反查索引 =====================

_mention_index = None   # 条目名 → 提到它的条目 [{name, category}]（懒加载+缓存）
_mention_loaded = False


def build_mention_index(force=False):
    """扫描知识库，建立"谁提到了 X"反查索引。

    原理：条目 A 的 full_text 里出现了条目 B 的名字 → B 被 A 提及。
    用于"解锁武陵需要什么条件"——解锁条件往往写在**别的任务条目**里
    （"完成后解锁武陵"），而不是武陵条目本身，单次检索捞不到。
    索引: mention_index[被提及名] = [{name: 提及者条目名, category: ...}, ...]
    缓存到 output/mention_index.json（约几百 KB，可复用）。
    """
    global _mention_index, _mention_loaded
    cache_path = os.path.join(ROOT, "output", "mention_index.json")
    if not force and _mention_loaded:
        return _mention_index
    if not force and os.path.exists(cache_path):
        try:
            with open(cache_path, encoding="utf-8") as f:
                _mention_index = json.load(f)
            _mention_loaded = True
            return _mention_index
        except (OSError, ValueError):
            pass
    kb = _get_kb_names()
    # 被提及名集合（长度>=2，排除超长条目名，减少误匹配）
    names = sorted([n for n in kb if len(n) >= 2 and len(n) <= 12], key=len, reverse=True)
    index = {}
    for mentioner, info in kb.items():
        text = info.get("full_text") or ""
        if not text:
            continue
        # 只匹配长度>=3 的名称（2 字名易误伤，如"清水"到处出现）
        for n in names:
            if len(n) < 3:
                continue
            if n in text:
                index.setdefault(n, []).append({"name": mentioner, "category": info.get("category", "")})
    # 去重 + 排序（提及者多的排前）
    for n in index:
        seen = {}
        for e in index[n]:
            seen.setdefault(e["name"], e)
        index[n] = sorted(seen.values(), key=lambda e: e["name"])
    _mention_index = index
    _mention_loaded = True
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)
    return index


def mention_lookup(query, limit=6):
    """mention 反查：从查询抽实体 → 找到"谁提到了它"的条目（含全文）。

    "解锁武陵地区需要什么条件" → 抽"武陵" → 找到提到武陵的任务/地图条目
    → 返回这些条目的全文（解锁条件大概率写在里面）。
    返回 [{meta, text, _mention}] 或 []。
    """
    name, info = extract_kb_entity(query)
    if not name:
        # 也试配方库实体名
        name2, _k2 = extract_item_name(query)
        name = name2 or name
    if not name or len(name) < 2:
        return []
    index = build_mention_index()
    mentioners = index.get(name, [])
    out = []
    for m in mentioners[:limit]:
        # 提及者条目全文（作为额外上下文）
        kb = _get_kb_names()
        info2 = kb.get(m["name"])
        text = (info2 or {}).get("full_text") or ""
        if not text:
            continue
        out.append({
            "meta": {"name": m["name"], "category": m["category"], "item_id": "", "chunk_index": 0},
            "text": text, "score": 0.9, "vector_sim": 0.9, "bm25_score": 0.0,
            "_mention": True,
        })
    return out


# ===================== ② 查询改写 + 全文关键词检索 =====================

# 常见地名/区域词（从知识库条目名里统计的"地区"类词，供全文检索定位）
PLACE_WORDS = ["武陵", "首墩", "藏剑谷", "应龙关", "北部禁区", "迷踪林", "景玉谷",
               "四号谷地", "帝江号", "清波寨", "枢纽区", "矿脉源区", "源石研究园",
               "供能高地", "试验园区", "石涧崖", "武陵城", "盈天台"]


def extract_place(query):
    """从查询中抽取地名/区域词（"解锁武陵地区"→"武陵"）。返回 str 或 None。"""
    q = query or ""
    for p in sorted(PLACE_WORDS, key=len, reverse=True):
        if p in q:
            return p
    return None


def keyword_search(keywords, category=None, limit=8):
    """全文关键词检索：在知识库条目名+全文里找含关键词的条目。

    keywords: 词列表（如 ["武陵", "解锁"]）；长串自动拆成 2 字以上片段。
    相关度打分：名称含词权重高、全文含词权重低；全部关键词都出现才返回。
    返回 [{name, category, full_text, _kw_score}]。
    """
    # 拆词：把长词/长串切成 2+ 字片段（"武陵地区解锁条件"→[武陵,地区,解锁,条件]）
    terms = []
    for k in keywords:
        k = (k or "").strip()
        if not k:
            continue
        if len(k) <= 8:
            terms.append(k)
        else:
            # 长串：按 2-4 字滑动切块，保留含"解锁/开放/条件/任务/前往"等语义词的块
            for i in range(len(k) - 1):
                chunk = k[i:i + 4]
                if len(chunk) >= 2 and chunk not in terms:
                    terms.append(chunk)
    if not terms:
        return []
    # 分类加权：解锁/开放/条件类信息通常在 任务/活动/新人入门 里，
    # 干员/武器/物品 的人物设定也常出现地名，但通常与"解锁"无关 → 降权
    PRIORITY_CATS = {"任务": 3, "活动": 2, "新人入门": 2, "百科速览": 2, "档案库": 1}
    PENALTY_CATS = {"干员": -2, "武器": -2, "物品": -2, "装扮": -2, "蚀刻章": -2,
                    "贵重品库": -1, "系统蓝图": -1, "装备": -1, "威胁": -1}
    entries = _load_all_kb_entries()
    scored = []
    for e in entries:
        if category and e["category"] != category:
            continue
        name = e["name"] or ""
        text = e["full_text"] or ""
        hay = name + " " + text
        hit_terms = [t for t in terms if t in hay]
        if len(hit_terms) < max(1, len(terms) * 0.6):
            continue
        # 相关度：名称命中词权重 3，全文命中权重 1，分类加权
        score = sum(3 if t in name else 1 for t in hit_terms)
        score += PRIORITY_CATS.get(e["category"], 0) + PENALTY_CATS.get(e["category"], 0)
        scored.append((score, len(name), name, e))
    scored.sort(key=lambda x: (-x[0], x[1]))
    out = []
    for _s, _l, _n, e in scored[:limit]:
        out.append({**e, "_kw_score": _s})
    return out


PLAN_TYPES = {"recipe", "device", "enum", "factual", "relation", "preference",
              "comparison", "numeric", "open"}
PLAN_ROUTES = {"entity_direct", "rag", "keyword", "mention", "graph",
               "relationship_evidence", "recipe", "enum"}


def _clean_plan_list(value, limit, max_chars=60):
    """把模型返回的列表压缩成安全、去重、有限长的字符串列表。"""
    out = []
    for item in value if isinstance(value, list) else []:
        item = str(item or "").strip()
        if not item or len(item) > max_chars or item in out:
            continue
        out.append(item)
        if len(out) >= limit:
            break
    return out


def semantic_plan(query, max_sub=3):
    """用一次受约束的 LLM 调用生成检索计划；失败时返回确定性降级计划。

    规划器只决定“问题在问什么、该用哪些检索词和检索器”，不产出事实答案，
    因而最终结论仍必须来自结构化数据、原文或 RAG 命中。
    """
    q = (query or "").strip()
    if not q:
        return {"question_type": "open", "topic": "", "entities": [], "keywords": [],
                "search_queries": [], "routes": ["rag"], "needs_graph": False,
                "planner_method": "empty"}
    place = extract_place(q)
    entity, _info = extract_kb_entity(q)
    fallback_queries = ([f"{place} 解锁", f"{place} 开放条件", f"{place} 前置任务"]
                        if place else [q])
    fallback = {
        "question_type": "open", "topic": q, "entities": [entity] if entity else [],
        "keywords": [place] if place else [], "search_queries": fallback_queries[:max_sub],
        "routes": ["entity_direct", "rag", "keyword", "mention"],
        "needs_graph": False, "planner_method": "fallback",
    }
    if llm.available():
        try:
            d = llm.chat_json(
                "分析下面的游戏知识库问题并生成检索计划，只输出 JSON。你不能回答问题，也不能"
                "把猜测的答案写进关键词。要同时考虑动词和对象，例如‘喜欢吃什么’的主题是饮食偏好，"
                "不是人物关系；‘喜欢谁/怎么看某人’才是关系解读。检索词可以使用问题原词和通用同义词，"
                "并必须保留决定主题的核心动词（如吃、穿、用、去），不要只留下抽象分类名。\n"
                f"问题：{q}\n"
                "question_type 只能是 recipe/device/enum/factual/relation/preference/"
                "comparison/numeric/open；routes 只能从 entity_direct/rag/keyword/mention/"
                "graph/relationship_evidence/recipe/enum 中选择。\n"
                '{"question_type":"preference","topic":"饮食偏好","entities":["人物名"],'
                '"keywords":["吃","食物","饮食","喜欢"],"search_queries":["人物名 吃 饮食偏好"],'
                '"routes":["entity_direct","rag","keyword"],"needs_graph":false}',
                system="你是检索规划器，只输出 JSON；计划中的词不是事实证据。",
                temperature=0.1, max_tokens=350)
            question_type = str(d.get("question_type") or "open").strip()
            if question_type not in PLAN_TYPES:
                question_type = "open"
            known_names = _get_kb_names()
            entities = [x for x in _clean_plan_list(d.get("entities"), 3, 30) if x in known_names]
            if entity and entity not in entities:
                entities.insert(0, entity)
            routes = [x for x in _clean_plan_list(d.get("routes"), 6, 30) if x in PLAN_ROUTES]
            queries = _clean_plan_list(d.get("search_queries"), max_sub, 60)
            return {
                "question_type": question_type,
                "topic": str(d.get("topic") or q).strip()[:40],
                "entities": entities[:3],
                "keywords": _clean_plan_list(d.get("keywords"), 8, 20),
                "search_queries": queries or fallback_queries[:max_sub],
                "routes": routes or ["entity_direct", "rag", "keyword"],
                "needs_graph": bool(d.get("needs_graph")),
                "planner_method": "llm",
            }
        except Exception:
            pass
    return fallback


def query_expand(query, max_sub=3, plan=None):
    """兼容入口：从语义检索计划中取子查询。"""
    plan = plan or semantic_plan(query, max_sub=max_sub)
    return (plan.get("search_queries") or [query])[:max_sub]


def multi_search(query, top_k=5, plan=None):
    """多路检索：语义计划 + 原查询 → RAG/全文关键词/mention，合并去重。

    用于"解锁武陵"这类开放问题——单一查询捞不到间接信息时，
    多路并进再合并，把散落在不同条目的线索凑齐。
    """
    plan = plan or semantic_plan(query)
    subs = query_expand(query, plan=plan)
    # 图/结构化路线未命中后仍可回退文本；已有文本路线则严格执行计划。
    routes = set(plan.get("routes") or []) & {"entity_direct", "rag", "keyword", "mention"}
    if not routes:
        routes = {"entity_direct", "rag", "keyword"}
    all_hits = []
    seen = {}

    def _add(h):
        name = h["meta"].get("name") or ""
        key = (name, h["meta"].get("category") or "")
        if key in seen:
            # 同一来源先被向量召回时，仍允许全文关键词结果补全正文和相关性标记。
            index = seen[key]
            if h.get("_keyword") and not all_hits[index].get("_direct"):
                all_hits[index] = h
            return
        seen[key] = len(all_hits)
        all_hits.append(h)

    if "entity_direct" in routes:
        for h in kb_direct_hits(query, top_n=1):
            _add(h)
    # 1. 原查询 RAG；实体直取由独立路线控制。
    if "rag" in routes:
        for h in rag_search(query, top_k=top_k, direct_fallback=False):
            _add(h)
    # 规划器给出的主题词用于全文补召回。按“实体 + 单个主题词”分别搜索，避免
    # 把过多同义词做成必须同时命中的 AND 条件。
    plan_entities = plan.get("entities") or []
    for keyword in (plan.get("keywords") or []) if "keyword" in routes else []:
        # 有明确实体时不再用“吃/喜欢”等单字全库补召回，避免无关任务挤占上下文。
        keyword_sets = [[entity, keyword] for entity in plan_entities] if plan_entities else [[keyword]]
        for kw_list in keyword_sets:
            for e in keyword_search(kw_list, limit=3):
                _add({"meta": {"name": e["name"], "category": e["category"],
                                "item_id": e["item_id"], "chunk_index": 0},
                      "text": e["full_text"], "score": 0.85, "vector_sim": 0.85,
                      "bm25_score": 0.0, "_keyword": True})
    # 2. 子查询：RAG + 全文关键词 + mention
    place = extract_place(query)
    for sub in subs:
        if "rag" in routes:
            for h in rag_search(sub, top_k=3, direct_fallback=False):
                _add(h)
        # 全文关键词：地名 + 条件词（子查询拆分后的词）
        if place and "keyword" in routes:
            cond_words = [w for w in ["解锁", "开放", "条件", "前往", "任务", "完成", "进入"] if w in sub]
            for kw_list in ([[place] + cond_words, [place]]):
                for e in keyword_search(kw_list, limit=3):
                    _add({"meta": {"name": e["name"], "category": e["category"], "item_id": e["item_id"],
                                   "chunk_index": 0},
                          "text": e["full_text"], "score": 0.85, "vector_sim": 0.85,
                          "bm25_score": 0.0, "_keyword": True})
        # mention 反查
        if "mention" in routes:
            for h in mention_lookup(sub, limit=3):
                _add(h)
    # 实体全文、实体+主题关键词优先；仅仅提到名字不应挤掉主题证据。
    def _rank(h):
        if h.get("_direct"):
            return 0
        if h.get("_keyword"):
            return 1
        if h.get("_mention"):
            return 2
        return 3
    all_hits.sort(key=_rank)
    return all_hits[:max(top_k + 3, 10)]


# “喜欢/中意/信任”通常不是 Wiki 的结构化事实字段。此类问题先定位人物，再从原文
# 提取包含关系对象和态度线索的局部证据，不把一次模型解读永久写入图谱。
INTERPRETIVE_WORDS = ("喜欢", "中意", "在意", "讨厌", "信任", "敬重", "害怕", "态度", "怎么看", "感情",
                      "可爱", "漂亮", "帅", "有趣")
GENERIC_RELATION_TARGETS = ("管理员", "终末地工业", "罗德岛")
RELATION_CUE_WORDS = ("妹妹", "哥哥", "姐姐", "弟弟", "父亲", "母亲", "师父", "徒弟", "朋友", "队友")


def is_interpretive_relation(query):
    """识别需要原文解读、不能直接固化为图谱事实的关系问题。"""
    q = query or ""
    if not any(word in q for word in INTERPRETIVE_WORDS):
        return False
    known_entities = [name for name in _get_kb_names() if name and name in q]
    # “喜欢/讨厌”本身不等于人物关系；还要有第二个人物、泛化关系对象或亲属/队友线索。
    # 因而“喜欢吃什么”会走偏好检索，“喜欢佩丽卡吗”才走关系证据路线。
    return (len(known_entities) >= 2 or
            any(word in q for word in GENERIC_RELATION_TARGETS) or
            any(word in q for word in RELATION_CUE_WORDS))


def relationship_evidence_hits(query, limit=8):
    """为人物态度/性格判断抽取可读证据窗口，而非生成事实边。"""
    q = query or ""
    kb = _get_kb_names()
    entity_names = sorted([n for n in kb if n and n in q], key=len, reverse=True)
    targets = entity_names[:2] + [x for x in GENERIC_RELATION_TARGETS if x in q]
    targets = list(dict.fromkeys(targets))
    if not targets:
        return []
    candidates = []
    # 主人物条目优先，同时搜索任务/档案中两者共同出现的情节证据。
    for entry in _load_all_kb_entries():
        text = entry.get("full_text") or ""
        if not text or not any(t in text or t == entry.get("name") for t in targets):
            continue
        units = [u.strip() for u in __import__("re").split(r"\n+|(?<=[。！？!?])", text) if u.strip()]
        for i, unit in enumerate(units):
            window = "\n".join(units[max(0, i - 1):min(len(units), i + 2)])
            target_hits = sum(t in window for t in targets)
            attitude_hits = sum(w in window for w in INTERPRETIVE_WORDS)
            relation_hits = sum(w in window for w in RELATION_CUE_WORDS if w in q)
            dialogue_bonus = int("管理员" in window or "档案" in text or entry.get("category") == "任务")
            score = target_hits * 3 + attitude_hits * 2 + relation_hits * 4 + dialogue_bonus
            if target_hits and score >= 4:
                candidates.append((score, len(window), entry, window))
    candidates.sort(key=lambda x: (-x[0], x[1]))
    out, seen = [], set()
    for score, _length, entry, window in candidates:
        key = (entry["name"], window)
        if key in seen:
            continue
        seen.add(key)
        out.append({
            "meta": {"name": entry["name"], "category": entry["category"],
                     "item_id": entry["item_id"], "chunk_index": 0},
            "text": window, "score": min(1.0, score / 10), "vector_sim": 1.0,
            "bm25_score": 0.0, "_relationship_evidence": True,
        })
        if len(out) >= limit:
            break
    return out


def _device_by_name(recipes, item_index, name):
    """设备名 → 设备配方列表（不存在返回 None）。"""
    by_name = {}
    for r in recipes:
        by_name.setdefault(str(r.get("machine_id") or ""), r["machine"])
    dev = {m.strip(): mid for mid, m in by_name.items()}
    if name not in dev:
        return None
    mid = dev[name]
    dev_recs = [r for r in recipes if str(r.get("machine_id") or "") == mid]
    return [{
        "machine": r["machine"], "duration": r.get("duration", 1.0),
        "inputs": [{"name": item_index.get(x["item_id"], {}).get("name", x["name"]),
                    "count": x["count"]} for x in r["inputs"]],
        "outputs": [{"name": item_index.get(x["item_id"], {}).get("name", x["name"]),
                     "count": x["count"]} for x in r["outputs"]],
    } for r in dev_recs]


def _recipe_cards(item_index, producers, limit=2):
    """物品的配方卡片（最多 limit 个）。"""
    out = []
    for r in producers[:limit]:
        out.append({
            "machine": r["machine"], "duration": r.get("duration", 1.0),
            "inputs": [{"name": item_index.get(x["item_id"], {}).get("name", x["name"]),
                        "count": x["count"]} for x in r["inputs"]],
            "outputs": [{"name": item_index.get(x["item_id"], {}).get("name", x["name"]),
                         "count": x["count"]} for x in r["outputs"]],
        })
    return out


def recipe_lookup(query, intent=None):
    """配方/设备意图 → 结构化配方库直查。返回结果 dict 或 None。

    结果形态:
      {"route": "recipe", "item": 物品名, "recipes": [配方...]}
      {"route": "device", "device": 设备名, "recipes": [配方...]}
      {"route": "device_products", "keyword": "电池", "matches": [设备+物品列表]}
      {"route": "ambiguous", "item": 短名, "candidates": [完整名...]}
    """
    recipes, item_index = _get_recipes()
    from recipe_index import find_item_ids_by_name

    # 1. 完整名称匹配（含设备名）
    name, kind = extract_item_name(query)
    if name:
        if kind == "device":
            cards = _device_by_name(recipes, item_index, name)
            if cards:
                return {"route": "device", "device": name, "recipes": cards}
        else:
            tids = find_item_ids_by_name(recipes, name)
            if len(tids) > 1:
                cands = sorted({item_index[i]["name"].strip() for i in tids})
                return {"route": "ambiguous", "item": name, "candidates": cands}
            if len(tids) == 1:
                prod = item_index[tids[0]].get("produce_by", [])
                if prod:
                    return {"route": "recipe", "item": item_index[tids[0]]["name"].strip(),
                            "recipes": _recipe_cards(item_index, prod)}
                return None  # 无配方物品 → 回退 RAG/知识库

    # 2. 设备产物反查："什么设备能生产电池" → 找出产物含"电池"的设备
    if intent == "设备" or kind == "device":
        import re as _re
        m = _re.search(r"(?:生产|制造|造|做|加工|合成|产出|提炼|冶炼|制作)(.+?)(?:[呢？?。]|$)", query)
        keyword = (m.group(1).strip() if m else "").rstrip("的了")
        if keyword:
            # 找产物名包含关键词的物品
            prod_items = {}
            for r in recipes:
                for o in r["outputs"]:
                    if keyword in o["name"]:
                        prod_items.setdefault(o["name"], {"device": r["machine"], "output": o["name"],
                                                          "count": o["count"]})
            if prod_items:
                return {"route": "device_products", "keyword": keyword,
                        "matches": [{"device": v["device"], "output": v["output"], "count": v["count"]}
                                    for k, v in sorted(prod_items.items())][:10]}

    # 3. 短名子串回退："灼铜" → 灼铜块/气态灼铜/灼铜零件…
    tids = find_item_ids_by_name(recipes, query.strip())
    if len(tids) > 1:
        cands = sorted({item_index[i]["name"].strip() for i in tids})
        return {"route": "ambiguous", "item": query.strip(), "candidates": cands}
    return None


# ===================== RAG 检索 =====================

# 枚举查询：主题关键词 → (目标分类, 名称过滤关键词列表)
# 用于"有哪些/列举/所有"类问题——纯向量检索对枚举失效，改为知识库分类内过滤枚举。
ENUM_RULES = [
    # 主线任务
    ("主线任务", "任务", ["第一章", "第二章", "第三章", "第四章", "序章", "进程", "终章"]),
    ("主线任务", "任务", ["主线"]),
    # 支线/日常任务
    ("任务", "任务", ["任务", "委托", "日常", "周常"]),
    # 干员
    ("干员", "干员", ["干员"]),
    # 武器
    ("武器", "武器", ["武器"]),
    # 装备
    ("装备", "装备", ["装备"]),
    # 活动
    ("活动", "活动", ["活动"]),
    # 敌人/威胁
    ("威胁", "威胁", ["威胁", "敌人", "怪物", "Boss"]),
]

ENUM_QUERY_PAT = (
    r"有(哪些|哪些任务|什么任务|哪些关卡|什么关卡|哪些干员|哪些武器|哪些活动|哪些装备)"
    r"|列举|列一下|所有|全部|有哪些|有哪些任务|是什么任务|共(有)?几|几(章|个|类)|至今(为止|为止的)"
)


def _load_all_kb_entries():
    """加载全部知识源（分类条目 + 干员中文语音）的懒加载缓存。"""
    if not hasattr(_load_all_kb_entries, "_cache"):
        import glob as _glob
        entries = []
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
                    entries.append({"name": (d.get("name") or "").strip(),
                                    "category": d.get("category", ""),
                                    "item_id": str(d.get("item_id") or ""),
                                    "full_text": (d.get("full_text") or "")})
        try:
            from build_rag import load_operator_audio_records
            for d in load_operator_audio_records(os.path.join(ROOT, "output", "operator_details.json")):
                entries.append({"name": d["name"], "category": d["category"],
                                "item_id": d["item_id"], "full_text": d["full_text"]})
        except (OSError, ValueError, ImportError):
            pass
        _load_all_kb_entries._cache = entries
    return _load_all_kb_entries._cache


def enum_lookup(query, limit=40):
    """枚举查询：按主题关键词在知识库分类内过滤，返回匹配条目名列表。

    "终末地至今为止的主线任务有哪些" → 任务分类中含 第一章/序章/进程 的条目名
    "游戏里有哪些干员" → 干员分类全部条目
    返回 {"label": "主线任务", "names": [...]} 或 None（非枚举查询）。
    """
    import re as _re
    q = (query or "").strip()
    if not q or not _re.search(ENUM_QUERY_PAT, q):
        return None
    entries = _load_all_kb_entries()
    for label, category, keywords in ENUM_RULES:
        # 宽松匹配主题：查询里出现规则 label 或关键词之一
        if not any(k in q for k in [label] + keywords):
            continue
        matched = []
        if category in keywords:
            # 主题即分类（干员/武器/活动/装备…）：直接枚举该分类全部条目
            # （条目名是"佩丽卡/四二式·肃阵"，本身不含"干员/武器"字样）
            for e in entries:
                if e["category"] == category and e["name"] and e["name"] not in matched:
                    matched.append(e["name"])
        else:
            # 主题是分类子集（主线任务 ⊂ 任务）：按名称关键词过滤
            for e in entries:
                if e["category"] != category:
                    continue
                n = e["name"]
                if any(k in n for k in keywords) and n not in matched:
                    matched.append(n)
        if matched:
            return {"label": label, "category": category,
                    "names": sorted(matched)[:limit]}
    return None


def rag_search(query, top_k=5, entity_boost=True, direct_fallback=True):
    """RAG 混合检索（向量+BM25→RRF），带实体加权与知识库直取兜底。

    entity_boost:  抽到实体时把实体名注入 BM25 查询（"诀"→ 干员条目顶到前排）
    direct_fallback: 实体在知识库有条目且检索 top1 与实体不一致时，直接用条目全文当上下文
    """
    hits = _get_retriever().search(query, top_k=top_k)
    if not entity_boost and not direct_fallback:
        return hits

    name, info = extract_kb_entity(query)
    if not name or not info:
        # 也试试配方库实体（如"重息壤"在配方库，不在知识库同名？其实都在）
        name2, _kind2 = extract_item_name(query)
        if not name2:
            return hits
        name = name2

    # 实体加权重搜：实体名 + 原查询，BM25 更容易把实体条目顶上来
    boosted = _get_retriever().search(f"{name} {query}", top_k=top_k)

    # 主条目判定：只认精确同名（"诀"=="诀(干员)"）。
    # 注意"诀的信物/头像·诀"是独立条目不是衍生，不算主条目——
    # 用户问"诀升级材料"需要的是干员主条目的[精英化]数据。
    def _is_main_entity(hit_name_):
        hn = (hit_name_ or "").strip()
        return hn == name

    def _contains_entity(hs):
        return any(_is_main_entity(h["meta"].get("name")) for h in hs[:top_k])

    # 实体在知识库存在 → 实体完整条目全文打头（绕开 chunk 切分丢失表格），
    # 再补上检索结果里的其他相关条目（去重），保证上下文既权威又全面。
    direct = kb_direct_hits(query, top_n=1) if direct_fallback else []
    if direct:
        merged = list(direct)
        seen = {name}
        for h in (hits + boosted):
            hn = h["meta"].get("name") or ""
            if hn not in seen and len(merged) < top_k:
                seen.add(hn)
                merged.append(h)
        return merged

    if _contains_entity(hits):
        return hits
    if _contains_entity(boosted):
        return boosted
    return hits or boosted


# ===================== 答案生成 =====================

GEN_SYSTEM = (
    "你是《明日方舟：终末地》百科助手。根据提供的资料回答用户问题，要求：\n"
    "1. 只基于提供的资料，不要编造资料外的内容\n"
    "2. 回答末尾用 [来源1] 标注依据哪条资料\n"
    "3. 若资料不足以回答，明确说'资料中未找到相关内容'\n"
    "4. 对喜欢、性格、态度、动机等解释性问题，必须分成‘原文明确事实’、"
    "‘基于证据的合理解读’和‘资料不足’，不得把解读伪装成设定事实\n"
    "5. 复合问题必须逐项回答；某一小问资料不足时，只说明该小问不足，不能拒绝其他有证据的小问\n"
    "6. 简洁，中文回答"
)


QUERY_STOP_WORDS = {
    "什么", "怎么", "怎样", "如何", "是不是", "是否", "来着", "叫啥", "叫什么", "哪个",
    "哪里", "为啥", "为什么", "一下", "介绍", "告诉", "这个", "那个", "可以", "觉得",
}


def extract_focus_terms(query):
    """提取用于长文定位的实体词和语义词，不依赖固定人物或固定关系。"""
    q = (query or "").strip()
    if not q:
        return []
    terms = []
    try:
        import jieba
        terms.extend(x.strip() for x in jieba.lcut(q) if x.strip())
    except Exception:
        terms.extend(re.findall(r"[\u4e00-\u9fffA-Za-z0-9·]{2,}", q))
    # 已知实体名通常是最强定位词；关系和评价词保证复合问题的每个维度都参与选段。
    terms.extend(n for n in _get_kb_names() if n and n in q)
    terms.extend(w for w in RELATION_CUE_WORDS + INTERPRETIVE_WORDS if w in q)
    cleaned = []
    for term in terms:
        term = term.strip("，。！？?、：:（）()的了呢吗呀她他它")
        if len(term) < 2 or term in QUERY_STOP_WORDS or term in cleaned:
            continue
        cleaned.append(term)
    return sorted(cleaned, key=len, reverse=True)


def focus_long_context(text, query, max_chars=1800, max_windows=7):
    """从全文选取覆盖各查询词的分散证据窗口，避免永远只把前 1500 字交给 LLM。"""
    text = str(text or "")
    if len(text) <= max_chars:
        return text
    terms = extract_focus_terms(query)
    if not terms:
        return text[:max_chars]
    units = [u.strip() for u in re.split(r"\n+|(?<=[。！？!?])", text) if u.strip()]
    candidates = []
    for i, unit in enumerate(units):
        window = "\n".join(units[max(0, i - 1):min(len(units), i + 2)])
        covered = tuple(t for t in terms if t in window)
        if not covered:
            continue
        score = sum(5 + min(len(t), 8) for t in covered) + len(covered) * len(covered) * 3
        candidates.append({"i": i, "text": window, "covered": covered, "score": score})
    if not candidates:
        return text[:max_chars]

    selected, used_indexes, covered_terms = [], set(), set()
    # 先为每个查询词保留它的最佳证据，防止复合问题只覆盖得分最高的一个子问。
    for term in terms:
        if term in covered_terms:
            continue
        options = [c for c in candidates if term in c["covered"]]
        if not options:
            continue
        best = max(options, key=lambda c: (c["score"], -len(c["text"])))
        if best["i"] not in used_indexes and not any(abs(best["i"] - x) <= 2 for x in used_indexes):
            selected.append(best); used_indexes.add(best["i"]); covered_terms.update(best["covered"])
    for candidate in sorted(candidates, key=lambda c: (-c["score"], len(c["text"]))):
        if len(selected) >= max_windows:
            break
        if candidate["i"] in used_indexes or any(abs(candidate["i"] - x) <= 2 for x in used_indexes):
            continue
        selected.append(candidate); used_indexes.add(candidate["i"]); covered_terms.update(candidate["covered"])

    parts, size = [], 0
    for candidate in sorted(selected, key=lambda c: c["i"]):
        block = candidate["text"]
        if size + len(block) > max_chars:
            block = block[:max(0, max_chars - size)]
        if block:
            parts.append(block); size += len(block)
        if size >= max_chars:
            break
    return "\n…\n".join(parts) or text[:max_chars]


def gen_answer(query, hits, top_k=5):
    """用在线 LLM 基于检索片段生成带引用的回答。

    - 实体直取命中（_direct）：实体已确认在知识库，直接给完整条目，不拒答
    - 普通检索：top-1 相似度 < 阈值 → 诚实拒答
    """
    if not llm.available():
        return None
    top = hits[0] if hits else None
    if not top:
        return {"answer": "知识库中未找到足够相关的资料来回答这个问题。",
                "rejected": True, "hits": []}
    is_direct = bool(top.get("_direct"))
    # 多路合并片段（关键词/mention/直取）是人工确认的相关上下文，不因 top-1 vec 低拒答
    has_curated = any(h.get("_keyword") or h.get("_mention") or h.get("_direct") or
                      h.get("_relationship_evidence") for h in hits[:top_k])
    if not is_direct and not has_curated and top.get("vector_sim", 0) < 0.30:
        return {"answer": "知识库中未找到足够相关的资料来回答这个问题。",
                "rejected": True, "hits": hits[:top_k]}
    ctx = "\n\n".join(
        f"[来源{i+1}] (分类:{h['meta'].get('category')} 名称:{h['meta'].get('name')})\n"
        f"{focus_long_context(h['text'], query, max_chars=1800)}"
        for i, h in enumerate(hits[:top_k]))
    prompt = f"资料：\n{ctx}\n\n问题：{query}\n\n请回答："
    try:
        answer = llm.chat(prompt, system=GEN_SYSTEM, temperature=0.3, max_tokens=800)
    except Exception:
        return None
    return {"answer": answer, "rejected": False,
            "sources": [{"name": h["meta"].get("name"), "category": h["meta"].get("category"),
                         "score": h["score"]} for h in hits[:top_k]]}


def attach_generated_answer(result, query, hits, top_k, enabled):
    """按需生成答案并合并到路由结果；LLM 不可用或失败时保留原检索结果。"""
    if not enabled:
        return result
    generated = gen_answer(query, hits, top_k=top_k)
    if generated:
        result.update(generated)
    return result


# ===================== 入口 =====================

def ask(query, top_k=5, gen_answer_=False):
    """问答入口：确定性规则 → 一次语义规划 → 数据检索 → (可选)生成。"""
    q = (query or "").strip()
    if not q:
        return {"ok": False, "error": "查询为空"}
    # 这里只运行零成本规则，避免随后语义规划时产生第二次 LLM 意图调用。
    intent, conf, method = classify_query(q, allow_llm=False)

    # 0. 枚举查询："有哪些/列举/所有" → 知识库分类内过滤枚举
    #    （"终末地至今为止的主线任务有哪些" → 任务分类枚举主线）
    enum = enum_lookup(q)
    if enum:
        result = {"ok": True, "intent": intent or "枚举", "method": method,
                  "route_used": "enum", "enum": enum,
                  "names": enum["names"], "count": len(enum["names"])}
        if gen_answer_ and llm.available():
            enum_names = enum["names"][:40]
            names_list = "\n".join(f"[来源{i + 1}] {name}" for i, name in enumerate(enum_names))
            truncated_note = (f"这里只提供前 {len(enum_names)} 项用于整理，完整结果共 {len(enum['names'])} 项；"
                              "不得把当前清单说成完整清单。" if len(enum["names"]) > len(enum_names)
                              else f"当前清单包含完整的 {len(enum_names)} 项。")
            try:
                ans = llm.chat(
                    f"知识库中{enum['label']}相关条目总数：{len(enum['names'])}。\n"
                    f"{truncated_note}\n条目如下：\n{names_list}\n\n"
                    f"问题：{query}\n请基于这些条目整理成清晰的回答（有章节/分类就分组，"
                    "准确说明总数；清单被截断时必须明确说明只展示前若干项）。",
                    system=GEN_SYSTEM, temperature=0.3, max_tokens=800)
                result["answer"] = ans
                result["rejected"] = False
                result["sources"] = [
                    {"name": name, "category": enum["category"], "score": 1.0}
                    for name in enum_names
                ]
            except Exception:
                pass
        return result

    # 结构化直查条件：
    #   - 配方/设备意图 → 直接试
    #   - 意图不明（None）或纯名称查询（用户直接输入"天有洪炉"）→ 也试
    pure_name = extract_item_name(q)[0] == q
    if intent in ("配方", "设备") or intent is None or pure_name:
        direct = recipe_lookup(q, intent=intent)
        if direct:
            return {"ok": True, "intent": intent or "配方/设备", "method": method, **direct,
                    "route_used": "structured"}

    # 非确定性问题统一进行一次语义规划。规划只控制检索，不提供答案。
    plan = semantic_plan(q)
    type_to_intent = {"recipe": "配方", "device": "设备", "comparison": "比较",
                      "numeric": "数值", "enum": "枚举", "relation": "关系",
                      "preference": "偏好", "factual": "知识", "open": "知识"}
    if plan.get("planner_method") == "llm":
        # 宽规则只负责抢占能成功直查的路径；直查未命中后，以语义计划纠正宽规则误判。
        intent = type_to_intent.get(plan.get("question_type"), "知识")
        method = "semantic_plan"
    elif intent is None:
        intent = type_to_intent.get(plan.get("question_type"), "知识")
        method = "semantic_fallback"

    relation_planned = (plan.get("question_type") == "relation" or
                        "relationship_evidence" in (plan.get("routes") or []))
    if relation_planned or (plan.get("planner_method") != "llm" and is_interpretive_relation(q)):
        evidence = relationship_evidence_hits(q, limit=max(top_k, 8))
        graph_result = None
        try:
            from graph_search import graph_query
            graph_result = graph_query(q, top_k=top_k)
        except Exception:
            pass
        graph_hits = ((graph_result or {}).get("hits") or []) if (
            len((graph_result or {}).get("entities") or []) >= 2 or (graph_result or {}).get("predicate")) else []
        hits = (graph_hits + evidence + multi_search(q, top_k=top_k, plan=plan))[:max(top_k + 5, 12)]
        result = {"ok": True, "intent": "解释性关系", "method": "evidence_hybrid",
                  "route_used": "hybrid_relation", "graph": graph_result,
                  "semantic_plan": plan,
                  "interpretation_policy": "事实边与文本解读分离", "hits": hits}
        return attach_generated_answer(result, q, hits, max(top_k, 8), gen_answer_)

    # GraphRAG：明确关系/多跳问题优先查询带证据的图路径。没有路径时继续走原 RAG，
    # “图谱尚无证据”不等于“关系不存在”。
    graph_result = None
    try:
        from graph_search import graph_query, should_route_graph
        if plan.get("needs_graph") or "graph" in (plan.get("routes") or []) or should_route_graph(q):
            graph_result = graph_query(q, top_k=max(top_k, 5))
            if graph_result.get("paths"):
                result = {"ok": True, "intent": "关系", "method": "graph_rule",
                          "route_used": "graph", "graph": graph_result,
                          "hits": graph_result.get("hits") or []}
                return attach_generated_answer(result, q, result["hits"], top_k, gen_answer_)
    except Exception:
        graph_result = {"available": False, "paths": [], "error": "graph_unavailable"}

    # 其他意图 / 直查未命中 → 多路检索（RAG + 改写子查询 + 全文关键词 + mention）
    hits = multi_search(q, top_k=top_k, plan=plan)
    result = {"ok": True, "intent": intent or "未知", "method": method,
              "route_used": "rag", "semantic_plan": plan, "hits": hits}
    if graph_result is not None:
        result["graph_attempted"] = True
        result["graph"] = graph_result
    return attach_generated_answer(result, q, hits, top_k, gen_answer_)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--gen", action="store_true", help="启用 LLM 答案生成")
    ap.add_argument("--top-k", type=int, default=5)
    args = ap.parse_args()
    res = ask(args.query, top_k=args.top_k, gen_answer_=args.gen)
    print(json.dumps(res, ensure_ascii=False, indent=2))
