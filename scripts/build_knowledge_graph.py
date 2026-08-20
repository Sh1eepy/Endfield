# -*- coding: utf-8 -*-
"""从结构化知识库构建可追溯、可增量更新的轻量知识图谱。"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DB = os.path.join(ROOT, "output", "knowledge_graph", "graph.db")
SCHEMA_VERSION = "2"

TYPE_BY_CATEGORY = {
    "干员": "person", "任务": "quest", "武器": "weapon", "装备": "equipment",
    "物品": "item", "设备": "device", "活动": "event", "档案库": "archive",
}

# 只有结构化章节中的 entry 引用才转换为带语义的边；其余仍保留 REFERENCES。
# 这些映射描述“页面字段含义”，不依赖 LLM 猜测。
SECTION_PREDICATES = {
    ("任务", "任务奖励"): "REWARDS",
    ("任务", "解锁内容"): "UNLOCKS",
    ("干员", "武器推荐"): "RECOMMENDS_WEAPON",
    ("干员", "精英化"): "REQUIRES_MATERIAL",
    ("物品", "相关来源"): "OBTAINED_FROM",
    ("物品", "相关用途"): "USED_FOR",
    ("设备", "设备来源"): "OBTAINED_FROM",
    ("设备", "蓝图来源"): "OBTAINED_FROM",
    ("武器", "武器推荐"): "RECOMMENDED_FOR",
}


def content_hash(row):
    raw = "\n".join((str(row.get("name") or ""), str(row.get("category") or ""),
                     str(row.get("full_text") or "")))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def relation_id(subject_id, predicate, object_id, source_item_id, evidence):
    raw = "\x1f".join((subject_id, predicate, object_id, source_item_id, evidence))
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def load_rows(pattern="endfield_kb/*.jsonl"):
    rows = []
    for path in sorted(glob.glob(os.path.join(ROOT, pattern))):
        with open(path, encoding="utf-8") as fh:
            rows.extend(json.loads(line) for line in fh if line.strip())
    return rows


def connect(path=DEFAULT_DB):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def create_schema(con, reset=False):
    if reset:
        con.executescript("DROP TABLE IF EXISTS relations; DROP TABLE IF EXISTS aliases; "
                          "DROP TABLE IF EXISTS manifest; DROP TABLE IF EXISTS entities; DROP TABLE IF EXISTS meta;")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS entities(
      id TEXT PRIMARY KEY, canonical_name TEXT NOT NULL, entity_type TEXT NOT NULL,
      category TEXT NOT NULL DEFAULT '', source_item_id TEXT NOT NULL DEFAULT '', synthetic INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_entities_name ON entities(canonical_name);
    CREATE TABLE IF NOT EXISTS aliases(
      alias TEXT NOT NULL, entity_id TEXT NOT NULL, alias_kind TEXT NOT NULL DEFAULT 'alias',
      source_item_id TEXT NOT NULL DEFAULT '', evidence TEXT NOT NULL DEFAULT '',
      confidence REAL NOT NULL DEFAULT 1.0, review_status TEXT NOT NULL DEFAULT 'verified',
      PRIMARY KEY(alias, entity_id), FOREIGN KEY(entity_id) REFERENCES entities(id) ON DELETE CASCADE
    );
    CREATE INDEX IF NOT EXISTS idx_aliases_alias ON aliases(alias);
    CREATE TABLE IF NOT EXISTS relations(
      id TEXT PRIMARY KEY, subject_id TEXT NOT NULL, predicate TEXT NOT NULL, object_id TEXT NOT NULL,
      source_item_id TEXT NOT NULL, evidence TEXT NOT NULL, confidence REAL NOT NULL,
      extraction_method TEXT NOT NULL, review_status TEXT NOT NULL,
      FOREIGN KEY(subject_id) REFERENCES entities(id), FOREIGN KEY(object_id) REFERENCES entities(id)
    );
    CREATE INDEX IF NOT EXISTS idx_rel_subject ON relations(subject_id, predicate);
    CREATE INDEX IF NOT EXISTS idx_rel_object ON relations(object_id, predicate);
    CREATE INDEX IF NOT EXISTS idx_rel_source ON relations(source_item_id);
    CREATE TABLE IF NOT EXISTS manifest(
      source_item_id TEXT PRIMARY KEY, content_hash TEXT NOT NULL, name TEXT NOT NULL,
      category TEXT NOT NULL, relation_count INTEGER NOT NULL, updated_at TEXT NOT NULL
    );
    """)
    con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('schema_version',?)", (SCHEMA_VERSION,))


class GraphBuilder:
    def __init__(self, con, rows):
        self.con = con
        self.rows = rows
        self.by_item = {str(r.get("item_id") or ""): r for r in rows}
        self.by_name = {}
        for r in rows:
            self.by_name.setdefault(str(r.get("name") or "").strip(), str(r.get("item_id") or ""))

    def entity_id(self, name, entity_type="unknown"):
        name = (name or "").strip().strip("/· ")
        if not name:
            return None
        item_id = self.by_name.get(name)
        if item_id:
            return "kb:" + item_id
        digest = hashlib.sha1((entity_type + "\x1f" + name).encode("utf-8")).hexdigest()[:16]
        eid = f"syn:{entity_type}:{digest}"
        self.con.execute("INSERT OR IGNORE INTO entities(id,canonical_name,entity_type,synthetic) VALUES(?,?,?,1)",
                         (eid, name, entity_type))
        return eid

    def ensure_source_entities(self):
        for r in self.rows:
            item_id = str(r.get("item_id") or "")
            category = str(r.get("category") or "")
            self.con.execute("""INSERT OR REPLACE INTO entities
              (id,canonical_name,entity_type,category,source_item_id,synthetic) VALUES(?,?,?,?,?,0)""",
                             ("kb:" + item_id, str(r.get("name") or ""),
                              TYPE_BY_CATEGORY.get(category, "entry"), category, item_id))

    def add_relation(self, subject_id, predicate, object_id, source_item_id, evidence,
                     confidence=1.0, method="structured_rule", status="verified"):
        if not subject_id or not object_id or subject_id == object_id:
            return
        evidence = re.sub(r"\s+", " ", evidence or "").strip()[:500]
        rid = relation_id(subject_id, predicate, object_id, source_item_id, evidence)
        self.con.execute("""INSERT OR REPLACE INTO relations
          (id,subject_id,predicate,object_id,source_item_id,evidence,confidence,extraction_method,review_status)
          VALUES(?,?,?,?,?,?,?,?,?)""", (rid, subject_id, predicate, object_id, source_item_id,
                                           evidence, confidence, method, status))

    @staticmethod
    def block_values(text, label, stops):
        match = re.search(re.escape(label) + r"\s*\n(?P<body>.*?)(?=\n(?:" + "|".join(map(re.escape, stops)) + r")\s*[:：]?|\Z)",
                          text or "", re.S)
        if not match:
            return []
        values = []
        for line in match.group("body").splitlines():
            line = re.sub(r"^\s*[-•]\s*", "", line).strip()
            if line and line != "/" and not line.startswith("["):
                values.append(line)
        return values

    def extract_task(self, row):
        sid = "kb:" + str(row["item_id"])
        source = str(row["item_id"])
        text = row.get("full_text") or ""
        for person in self.block_values(text, "相关人物", ["任务道具", "解锁内容", "任务进程", "任务奖励"]):
            oid = self.entity_id(person, "person")
            self.add_relation(sid, "HAS_PARTICIPANT", oid, source, f"相关人物：{person}")
        for place in self.block_values(text, "地点", ["触发位置", "相关人物", "任务道具"]):
            oid = self.entity_id(place, "place")
            self.add_relation(sid, "LOCATED_IN", oid, source, f"地点：{place}")
            if place.endswith("城") and len(place) > 2:
                region = place[:-1]
                region_id = self.entity_id(region, "place")
                self.add_relation(oid, "PART_OF", region_id, source, f"地点层级：{place}属于{region}")

        lines = text.splitlines()
        for i, line in enumerate(lines):
            if "前置任务" not in line or "后续任务" not in line or i + 1 >= len(lines):
                continue
            headers = [x.strip() for x in line.split("|")]
            values = [x.strip() for x in lines[i + 1].split("|")]
            if len(headers) != len(values):
                continue
            for header, value in zip(headers, values):
                predicate = "PREVIOUS_QUEST" if "前置任务" in header else "NEXT_QUEST" if "后续任务" in header else None
                if not predicate or not value or value == "/":
                    continue
                value = re.sub(r"^[·•]\s*", "", value).strip()
                oid = self.entity_id(value, "quest")
                self.add_relation(sid, predicate, oid, source, f"{header}：{value}")
            break

    def extract_references(self, row):
        sid = "kb:" + str(row["item_id"])
        source = str(row["item_id"])

        def walk(value, section=""):
            if isinstance(value, dict):
                if value.get("t") == "entry" and value.get("id"):
                    oid = "kb:" + str(value["id"])
                    if str(value["id"]) in self.by_item:
                        predicate = SECTION_PREDICATES.get((str(row.get("category") or ""), section), "REFERENCES")
                        self.add_relation(sid, predicate, oid, source,
                                          f"{section or '正文'}引用：{value.get('x') or value['id']}")
                for child in value.values():
                    walk(child, section)
            elif isinstance(value, list):
                for child in value:
                    walk(child, section)

        for section, blocks in (row.get("sections_struct") or {}).items():
            walk(blocks, section)

    def extract_operator_affiliation(self, row, operator_details):
        op = operator_details.get(str(row["item_id"])) or {}
        for chapter in op.get("chapters") or []:
            for widget in chapter.get("widgets") or []:
                for fact in widget.get("facts") or []:
                    if fact.get("label") != "身份认证" or not fact.get("value"):
                        continue
                    org = str(fact["value"]).strip()
                    oid = self.entity_id(org, "organization")
                    self.add_relation("kb:" + str(row["item_id"]), "AFFILIATED_WITH", oid,
                                      str(row["item_id"]), f"身份认证：{org}")

    def extract_explicit_authority(self, row):
        """仅抽取明确的‘地区+正式职务’，不把‘带领队伍’之类动作误判为领袖。"""
        text = row.get("full_text") or ""
        person_id = "kb:" + str(row["item_id"])
        patterns = (
            r"(?P<place>[\u4e00-\u9fff]{2,8})科学发展区管代",
            r"我是(?P<place>[\u4e00-\u9fff]{2,8})的管代[，,](?P<person>[\u4e00-\u9fff]{2,6})",
        )
        for pattern in patterns:
            for match in re.finditer(pattern, text):
                place = match.group("place")
                # 第一种句式中“武陵”紧邻行政单位；第二种还校验自称姓名。
                if match.groupdict().get("person") and match.group("person") != row.get("name"):
                    continue
                place_id = self.entity_id(place, "place")
                self.add_relation(place_id, "AUTHORITY", person_id, str(row["item_id"]),
                                  match.group(0), confidence=1.0, method="explicit_title_rule")

    def extract_explicit_kinship(self, row):
        """抽取人物简介中明确点名的亲属关系；只接受“X的妹妹/哥哥”等直接句式。"""
        text = row.get("full_text") or ""
        sid = "kb:" + str(row["item_id"])
        patterns = (
            (r"(?P<relative>[\u4e00-\u9fff]{2,8})的妹妹", "YOUNGER_SISTER_OF"),
            (r"(?P<relative>[\u4e00-\u9fff]{2,8})的哥哥", "OLDER_BROTHER_OF"),
        )
        for pattern, predicate in patterns:
            for match in re.finditer(pattern, text):
                relative = match.group("relative")
                if relative not in self.by_name:
                    continue
                left = max(text.rfind(mark, 0, match.start()) for mark in ("\n", "。", "！", "？")) + 1
                ends = [text.find(mark, match.end()) for mark in ("\n", "。", "！", "？")]
                right = min((x for x in ends if x >= 0), default=min(len(text), match.end() + 120))
                evidence = text[left:right + 1].strip()
                self.add_relation(sid, predicate, self.entity_id(relative, "person"),
                                  str(row["item_id"]), evidence or match.group(0),
                                  confidence=1.0, method="explicit_kinship_rule")

    def extract_row(self, row, operator_details):
        category = str(row.get("category") or "")
        if category == "任务":
            self.extract_task(row)
        if category == "干员":
            self.extract_operator_affiliation(row, operator_details)
            self.extract_explicit_authority(row)
            self.extract_explicit_kinship(row)
        self.extract_references(row)

    def apply_curated_aliases(self, alias_path):
        if not os.path.exists(alias_path):
            return
        data = json.load(open(alias_path, encoding="utf-8"))
        for item in data.get("aliases") or []:
            eid = self.entity_id(item.get("canonical"), "person")
            if not eid:
                continue
            self.con.execute("""INSERT OR REPLACE INTO aliases
              (alias,entity_id,alias_kind,source_item_id,evidence,confidence,review_status)
              VALUES(?,?,?,?,?,1.0,?)""", (item["alias"], eid, item.get("kind", "alias"),
                                             str(item.get("source_item_id") or ""), item.get("evidence", ""),
                                             item.get("review_status", "human_verified")))

    def extract_recipes(self, recipe_path):
        """把精确 recipes.json 转成设备→原料/产物边，保留配方编号、数量和耗时证据。"""
        if not os.path.exists(recipe_path):
            return 0
        data = json.load(open(recipe_path, encoding="utf-8"))
        recipes = data.get("recipes", data if isinstance(data, list) else [])
        count = 0
        for recipe in recipes:
            machine = str(recipe.get("machine") or "").strip()
            mid = self.entity_id(machine, "device")
            source = "recipe:" + str(recipe.get("id") or machine)
            duration = recipe.get("duration")
            for predicate, key in (("DEVICE_USES_INPUT", "inputs"), ("DEVICE_PRODUCES", "outputs")):
                for item in recipe.get(key) or []:
                    oid = self.entity_id(str(item.get("name") or ""), "item")
                    evidence = f"配方{recipe.get('id') or ''}：{machine}；{item.get('name')}×{item.get('count')}；耗时{duration}"
                    before = self.con.total_changes
                    self.add_relation(mid, predicate, oid, source, evidence, method="recipe_rule")
                    count += self.con.total_changes > before
        return count


def build(db_path=DEFAULT_DB, incremental=False, inputs="endfield_kb/*.jsonl"):
    rows = load_rows(inputs)
    con = connect(db_path)
    create_schema(con, reset=not incremental)
    builder = GraphBuilder(con, rows)
    builder.ensure_source_entities()
    old = {r["source_item_id"]: r["content_hash"] for r in con.execute("SELECT source_item_id,content_hash FROM manifest")}
    new = {str(r.get("item_id") or ""): content_hash(r) for r in rows}
    changed = set(new) if not incremental else {k for k, v in new.items() if old.get(k) != v}
    deleted = set(old) - set(new)
    for source in sorted(changed | deleted):
        con.execute("DELETE FROM relations WHERE source_item_id=?", (source,))
        con.execute("DELETE FROM aliases WHERE source_item_id=? AND review_status!='human_verified'", (source,))
        con.execute("DELETE FROM manifest WHERE source_item_id=?", (source,))

    op_path = os.path.join(ROOT, "output", "operator_details.json")
    operator_details = (json.load(open(op_path, encoding="utf-8")).get("operators") or {}) if os.path.exists(op_path) else {}
    by_id = {str(r.get("item_id") or ""): r for r in rows}
    now = datetime.now(timezone.utc).isoformat()
    for source in sorted(changed):
        row = by_id[source]
        builder.extract_row(row, operator_details)
        count = con.execute("SELECT COUNT(*) FROM relations WHERE source_item_id=?", (source,)).fetchone()[0]
        con.execute("INSERT OR REPLACE INTO manifest VALUES(?,?,?,?,?,?)",
                    (source, new[source], row.get("name", ""), row.get("category", ""), count, now))
    builder.apply_curated_aliases(os.path.join(ROOT, "scripts", "graph_aliases.json"))
    # 配方体量很小且是独立结构化数据源：每次重建这些边，避免 KB 增量状态掩盖配方变化。
    con.execute("DELETE FROM relations WHERE extraction_method='recipe_rule'")
    builder.extract_recipes(os.path.join(ROOT, "output", "recipes.json"))
    con.execute("DELETE FROM entities WHERE synthetic=1 AND id NOT IN (SELECT subject_id FROM relations) "
                "AND id NOT IN (SELECT object_id FROM relations) AND id NOT IN (SELECT entity_id FROM aliases)")
    con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('built_at',?)", (now,))
    con.commit()
    summary = {
        "schema_version": SCHEMA_VERSION, "mode": "incremental" if incremental else "reset",
        "source_entries": len(rows), "changed_entries": len(changed), "deleted_entries": len(deleted),
        "entities": con.execute("SELECT COUNT(*) FROM entities").fetchone()[0],
        "aliases": con.execute("SELECT COUNT(*) FROM aliases").fetchone()[0],
        "relations": con.execute("SELECT COUNT(*) FROM relations").fetchone()[0],
        "built_at": now,
    }
    report = os.path.join(os.path.dirname(db_path), "build_report.json")
    with open(report, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    con.close()
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="output/knowledge_graph/graph.db")
    ap.add_argument("--inputs", default="endfield_kb/*.jsonl")
    ap.add_argument("--incremental", action="store_true")
    args = ap.parse_args()
    db = args.db if os.path.isabs(args.db) else os.path.join(ROOT, args.db)
    result = build(db, incremental=args.incremental, inputs=args.inputs)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
