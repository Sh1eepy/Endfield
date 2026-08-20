# -*- coding: utf-8 -*-
"""轻量 GraphRAG 检索：实体识别、关系路由、1-3 跳证据路径。"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from collections import deque

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "output", "knowledge_graph", "graph.db")

PREDICATE_LABELS = {
    "HAS_PARTICIPANT": "参与人物", "LOCATED_IN": "发生于", "PREVIOUS_QUEST": "前置任务",
    "NEXT_QUEST": "后续任务", "AFFILIATED_WITH": "所属组织", "REFERENCES": "引用",
    "PART_OF": "属于地区",
    "REWARDS": "奖励", "UNLOCKS": "解锁", "RECOMMENDS_WEAPON": "推荐武器",
    "REQUIRES_MATERIAL": "需要材料", "OBTAINED_FROM": "来源", "USED_FOR": "用于",
    "RECOMMENDED_FOR": "适合干员", "DEVICE_USES_INPUT": "使用原料",
    "DEVICE_PRODUCES": "生产", "AUTHORITY": "领导/负责",
    "YOUNGER_SISTER_OF": "妹妹", "OLDER_BROTHER_OF": "哥哥",
}

RELATION_HINTS = {
    "AUTHORITY": ("上司", "领导", "领袖", "首领", "负责人", "谁管", "管辖", "总代理"),
    "AFFILIATED_WITH": ("属于哪个组织", "所属组织", "隶属", "阵营", "身份认证"),
    "HAS_PARTICIPANT": ("相关人物", "谁参与", "参与过", "共同任务", "共同经历"),
    "LOCATED_IN": ("发生在哪", "地点", "位于", "在哪里"),
    "PREVIOUS_QUEST": ("前置任务", "之前任务", "前置"),
    "NEXT_QUEST": ("后续任务", "之后任务", "后续"),
    "REWARDS": ("奖励", "给什么"), "UNLOCKS": ("解锁什么", "开放什么"),
    "RECOMMENDS_WEAPON": ("推荐武器", "用什么武器"),
    "REQUIRES_MATERIAL": ("需要什么材料", "升级材料", "精英化材料"),
    "OBTAINED_FROM": ("怎么获得", "从哪里获得", "来源"),
    "USED_FOR": ("有什么用", "用途", "用来做什么"),
    "DEVICE_USES_INPUT": ("需要什么原料", "使用什么原料"),
    "DEVICE_PRODUCES": ("生产什么", "产出什么", "能做什么"),
    "YOUNGER_SISTER_OF": ("妹妹", "妹妹是谁", "妹妹叫啥", "妹妹叫什么"),
    "OLDER_BROTHER_OF": ("哥哥", "哥哥是谁", "哥哥叫啥", "哥哥叫什么"),
}

GRAPH_KEYWORDS = (
    "关系", "上司", "领导", "领袖", "首领", "负责人", "谁管", "管辖", "隶属", "所属", "组织", "阵营",
    "本名", "真名", "别名", "共同参与", "共同任务", "共同经历", "前置任务", "后续任务",
    "相关人物", "谁参与", "发生在哪", "奖励", "解锁什么", "推荐武器", "升级材料",
    "精英化材料", "怎么获得", "有什么用", "生产什么", "产出什么", "需要什么原料",
    "妹妹", "哥哥", "姐姐", "弟弟",
)


def should_route_graph(query):
    """判断问题是否明确要求实体关系或多跳路径。"""
    q = (query or "").strip()
    return bool(q and any(word in q for word in GRAPH_KEYWORDS))


class GraphRetriever:
    """从 SQLite 图谱解析实体、关系方向和最多三跳的证据路径。"""
    def __init__(self, db_path=DEFAULT_DB):
        self.db_path = db_path
        self.con = None
        self.entities = []
        self.aliases = []
        if os.path.exists(db_path):
            self.con = sqlite3.connect(db_path)
            self.con.row_factory = sqlite3.Row
            self.entities = [dict(x) for x in self.con.execute(
                "SELECT id,canonical_name,entity_type,category FROM entities "
                "WHERE length(canonical_name)>=2 OR entity_type='person'")]
            self.aliases = [dict(x) for x in self.con.execute(
                "SELECT a.alias,a.entity_id,a.alias_kind,a.evidence,e.canonical_name,e.entity_type "
                "FROM aliases a JOIN entities e ON e.id=a.entity_id")]

    def available(self):
        return self.con is not None

    def extract_entities(self, query, limit=4):
        if not self.con:
            return []
        found = {}
        for a in self.aliases:
            if a["alias"] in query:
                found[a["entity_id"]] = {"id": a["entity_id"], "name": a["canonical_name"],
                                          "type": a["entity_type"], "matched": a["alias"],
                                          "alias_kind": a["alias_kind"]}
        for e in sorted(self.entities, key=lambda x: len(x["canonical_name"]), reverse=True):
            if e["canonical_name"] in query:
                found.setdefault(e["id"], {"id": e["id"], "name": e["canonical_name"],
                                             "type": e["entity_type"], "matched": e["canonical_name"]})
            if len(found) >= limit:
                break
        candidates = sorted(found.values(), key=lambda x: len(x["matched"]), reverse=True)
        selected = []
        for candidate in candidates:
            if any(candidate["matched"] in current["matched"] for current in selected):
                continue
            selected.append(candidate)
        return selected[:limit]

    def predicate_hint(self, query):
        for predicate, words in RELATION_HINTS.items():
            if any(w in query for w in words):
                return predicate
        return None

    def alias_facts(self, query, entities):
        if not any(w in query for w in ("本名", "真名", "别名", "代号")):
            return []
        out = []
        for entity in entities:
            for row in self.con.execute(
                    "SELECT alias,alias_kind,evidence,confidence,review_status FROM aliases WHERE entity_id=?",
                    (entity["id"],)):
                out.append({"kind": "alias", "subject": entity["name"], "predicate": row["alias_kind"],
                            "object": row["alias"], "evidence": row["evidence"],
                            "confidence": row["confidence"], "review_status": row["review_status"]})
        return out

    def _edges(self, entity_id, predicate=None):
        sql = """SELECT r.*,s.canonical_name subject_name,o.canonical_name object_name,
                        s.entity_type subject_type,o.entity_type object_type
                 FROM relations r JOIN entities s ON s.id=r.subject_id JOIN entities o ON o.id=r.object_id
                 WHERE (r.subject_id=? OR r.object_id=?)"""
        params = [entity_id, entity_id]
        if predicate:
            sql += " AND r.predicate=?"
            params.append(predicate)
        sql += " ORDER BY r.confidence DESC, r.predicate, r.id"
        return [dict(x) for x in self.con.execute(sql, params)]

    def shortest_paths(self, start, target, max_hops=3, limit=8):
        paths = []
        queue = deque([(start, [], {start})])
        while queue and len(paths) < limit:
            node, path, visited = queue.popleft()
            if len(path) >= max_hops:
                continue
            for edge in self._edges(node):
                if edge["predicate"] == "REFERENCES" and max_hops > 1:
                    continue
                nxt = edge["object_id"] if edge["subject_id"] == node else edge["subject_id"]
                if nxt in visited:
                    continue
                new_path = path + [edge]
                if nxt == target:
                    paths.append(new_path)
                else:
                    queue.append((nxt, new_path, visited | {nxt}))
        return paths

    @staticmethod
    def render_path(path, start_id):
        parts = []
        current = start_id
        evidences = []
        confidence = 1.0
        sources = []
        for edge in path:
            forward = edge["subject_id"] == current
            left = edge["subject_name"] if forward else edge["object_name"]
            right = edge["object_name"] if forward else edge["subject_name"]
            label = PREDICATE_LABELS.get(edge["predicate"], edge["predicate"])
            arrow = "→" if forward else "←"
            parts.append(f"{left} {arrow}{label}{arrow} {right}")
            current = edge["object_id"] if forward else edge["subject_id"]
            evidences.append(edge["evidence"])
            sources.append(edge["source_item_id"])
            confidence *= float(edge["confidence"])
        return {"kind": "path", "path": "；".join(parts), "evidence": "；".join(evidences),
                "hops": len(path), "confidence": round(confidence, 4), "source_item_ids": sorted(set(sources))}

    def search(self, query, max_hops=3, top_k=8):
        if not self.con:
            return {"available": False, "entities": [], "paths": [], "hits": []}
        entities = self.extract_entities(query)
        facts = self.alias_facts(query, entities)
        predicate = self.predicate_hint(query)
        paths = []
        if len(entities) >= 2:
            start, target = entities[0], entities[1]
            for path in self.shortest_paths(start["id"], target["id"], max_hops=max_hops, limit=top_k):
                paths.append(self.render_path(path, start["id"]))
        elif len(entities) == 1 and not facts:
            start = entities[0]
            for edge in self._edges(start["id"], predicate=predicate)[:top_k]:
                paths.append(self.render_path([edge], start["id"]))

        for fact in facts:
            paths.insert(0, {"kind": "alias", "path": f"{fact['subject']} →{fact['predicate']}→ {fact['object']}",
                             "evidence": fact["evidence"], "hops": 1,
                             "confidence": fact["confidence"], "source_item_ids": []})
        hits = []
        for i, path in enumerate(paths[:top_k]):
            hits.append({
                "meta": {"name": f"关系路径{i + 1}", "category": "知识图谱", "item_id": "", "chunk_index": 0},
                "text": f"关系路径：{path['path']}\n证据：{path['evidence']}",
                "score": path["confidence"], "vector_sim": 1.0, "bm25_score": 0.0,
                "_graph": True,
            })
        return {"available": True, "entities": entities, "predicate": predicate,
                "paths": paths[:top_k], "hits": hits}


def graph_query(query, top_k=8, db_path=DEFAULT_DB):
    """安全打开图数据库并返回路径；数据库不可用时返回可降级结果。"""
    # 每次请求建立一个只读短连接，避免增量构建后实体缓存陈旧，也避免 Windows 文件锁。
    retriever = GraphRetriever(db_path)
    try:
        return retriever.search(query, top_k=top_k)
    finally:
        if retriever.con is not None:
            retriever.con.close()


def main():
    """图查询命令行入口。"""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--top-k", type=int, default=8)
    args = ap.parse_args()
    print(json.dumps(graph_query(args.query, args.top_k), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
