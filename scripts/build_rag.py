# -*- coding: utf-8 -*-
"""
build_rag.py — 把知识库 JSONL 构建/增量更新 RAG 索引（向量 + BM25 关键词）

用法:
    # 全量构建（基线）
    python scripts/build_rag.py --inputs "endfield_kb/*.jsonl" --reset
    # 增量更新（对比条目内容 hash，只重 embedding 变更条目 + 变更分类的 BM25 分片）
    python scripts/build_rag.py --inputs "endfield_kb/*.jsonl" --incremental

产出（默认 output/rag/）:
    chroma/                 ChromaDB 持久化向量库（metadata 含 item_id/name/category）
    chunks.json             chunk 清单（含条目级 content_hash，供增量对比/审计）
    bm25/{分类}.pkl         按分类分片的 BM25 倒排索引（更新只重建变更分类）
    report.txt              索引统计报告

增量更新原理（推荐组合）:
    1. 每条记录算 content_hash（md5(full_text)），写入 chunks.json
    2. --incremental 时对比新旧 hash：只有 hash 变化的条目重新 embedding
    3. ChromaDB upsert 只写变更 chunk / delete 移除删除条目
    4. BM25 按分类分片：仅重建变更条目所属分类的分片
    5. 向量库与 BM25 双路独立更新，避免全量重建

chunk 切分策略:
    条目整条优先（<=max_chars 字时 1 个 chunk）；超长按 sections 拆，
    每个 chunk 带条目级元信息（item_id/name/category），命中任何分块可回溯完整条目。
"""
import glob
import hashlib
import json
import os
import pickle
import shutil
import sys

# 离线模型：禁止联网检查 HF（否则超时/失败）
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

if sys.stdout:
    sys.stdout.reconfigure(encoding="utf-8")

import jieba
from rank_bm25 import BM25Okapi

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
BGE_QUERY_INSTRUCTION = "为这个句子生成表示以用于检索相关文章："
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 切分/前缀/元数据策略变化时递增；让 --incremental 能感知“代码变了但原文没变”。
INDEX_SCHEMA_VERSION = "3-fulltext-supplement-operator-audio"

# 游戏专有名词词典（gen_jieba_dict.py 生成），防止 jieba 切碎专有名词
_DICT_LOADED = False


def load_userdict():
    """加载项目自定义 jieba 词典（幂等）。"""
    global _DICT_LOADED
    if _DICT_LOADED:
        return
    dict_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "scripts", "dict_zh.txt")
    if os.path.exists(dict_path):
        jieba.load_userdict(dict_path)
    _DICT_LOADED = True


load_userdict()


def content_hash(text):
    """条目级内容指纹：full_text 的 md5。"""
    return hashlib.md5((text or "").encode("utf-8")).hexdigest()


def record_content_hash(record):
    """对所有会影响检索结果的条目内容和索引策略计算稳定指纹。"""
    payload = {
        "schema": INDEX_SCHEMA_VERSION,
        "name": record.get("name", ""),
        "category": record.get("category", ""),
        "full_text": record.get("full_text", ""),
        "sections": record.get("sections") or {},
    }
    return content_hash(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def load_operator_audio_records(path="output/operator_details.json"):
    """把干员中文语音文本规范化为可独立检索的知识记录。

    只收录“语音记录”章节中的中文文本，避免把同一句台词的英/日/韩译文和
    EP 演职员信息重复写入中文索引。每条语音使用稳定 audio id，支持增量更新。
    """
    if not path:
        return []
    path = path if os.path.isabs(path) else os.path.join(ROOT, path)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    records = []
    for operator_id, operator in (data.get("operators") or {}).items():
        operator_name = str(operator.get("name") or "").strip()
        if not operator_name:
            continue
        for chapter in operator.get("chapters") or []:
            chapter_title = str(chapter.get("title") or "").strip()
            if "语音" not in chapter_title:
                continue
            for widget in chapter.get("widgets") or []:
                widget_title = str(widget.get("title") or "").strip()
                for tab in widget.get("tabs") or []:
                    tab_title = str(tab.get("title") or "").strip()
                    # 当前数据的中文页以“中文：CV”命名；default 兼容旧采集格式。
                    if tab_title and not (tab_title.startswith("中文") or tab_title == "default"):
                        continue
                    for index, audio in enumerate(tab.get("audios") or []):
                        profile = str(audio.get("profile") or "").strip()
                        if not profile:
                            continue
                        audio_title = str(audio.get("title") or f"语音{index + 1}").strip()
                        audio_id = str(audio.get("id") or f"{index}").strip()
                        full_text = (f"干员：{operator_name}\n语音标题：{audio_title}\n"
                                     f"语音文本：{profile}")
                        records.append({
                            "item_id": f"{operator_id}:audio:{audio_id}",
                            "name": f"{operator_name}｜语音：{audio_title}",
                            "category": "干员语音",
                            "full_text": full_text,
                            "sections": {"语音文本": profile},
                            "source_kind": "operator_audio",
                            "operator_name": operator_name,
                            "audio_title": audio_title,
                            "audio_url": str(audio.get("url") or ""),
                        })
    return records


def load_records(paths, operator_details_path="output/operator_details.json"):
    """读取分类 JSONL 与干员中文语音；支持 glob，后出现的 ID 覆盖旧记录。"""
    files = []
    for p in paths:
        if glob.has_magic(p):
            files.extend(sorted(glob.glob(p)))
        else:
            files.append(p)
    records = []
    for p in files:
        default_cat = "设备" if ("设备" in os.path.basename(p) or "devices" in os.path.basename(p)) else "物品"
        with open(p, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                d = json.loads(line)
                records.append(
                    {
                        "item_id": str(d.get("item_id", "")),
                        "name": d.get("name", ""),
                        "category": d.get("category") or default_cat,
                        "full_text": d.get("full_text", ""),
                        "sections": d.get("sections") or {},
                    }
                )
    records.extend(load_operator_audio_records(operator_details_path))
    deduped = {}
    for record in records:
        deduped[(record["category"], record["item_id"])] = record
    return list(deduped.values())


def split_section_text(text, max_chars):
    """把单个超长 section 按行/段落切成 <=max_chars 的若干段。"""
    pieces, cur = [], ""
    for line in text.split("\n"):
        line = line.rstrip()
        if not line:
            continue
        if len(line) > max_chars:
            if cur:
                pieces.append(cur)
                cur = ""
            pieces.extend(line[i:i + max_chars] for i in range(0, len(line), max_chars))
            continue
        if len(cur) + len(line) + 1 > max_chars and cur:
            pieces.append(cur)
            cur = line
        else:
            cur = (cur + "\n" + line).strip() if cur else line
    if cur:
        pieces.append(cur)
    return pieces


def uncovered_full_text(full_text, sections):
    """返回未被结构化 sections 覆盖的全文行，防止描述/其他内容静默丢失。"""
    section_blob = "".join(
        "".join(str(value or "").split())
        for value in (sections or {}).values()
    )
    if not section_blob:
        return (full_text or "").strip()
    uncovered = []
    for line in (full_text or "").splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        normalized = "".join(stripped.split())
        # 标题本身信息量低；正文已存在于任一 section 时不重复索引。
        if normalized and normalized in section_blob:
            continue
        uncovered.append(stripped)
    return "\n".join(uncovered)


def split_chunks(record, max_chars):
    """条目级 chunk：短条目整条，超长条目按 sections 拆。"""
    full = (record.get("full_text") or "").strip()
    if not full:
        return []
    if len(full) <= max_chars:
        return [full]
    chunks = []
    cur = ""
    for sec_title, sec_text in (record.get("sections") or {}).items():
        sec_text = (sec_text or "").strip()
        if not sec_text:
            continue
        part = f"{sec_title}：{sec_text}" if sec_title and sec_title.strip() != " " else sec_text
        if len(part) > max_chars:
            if cur:
                chunks.append(cur)
                cur = ""
            for sub in split_section_text(part, max_chars):
                chunks.append(sub)
            continue
        if cur and len(cur) + len(part) + 1 > max_chars:
            chunks.append(cur)
            cur = part
        else:
            cur = (cur + "\n" + part).strip() if cur else part
    if cur:
        chunks.append(cur)
    supplemental = uncovered_full_text(full, record.get("sections") or {})
    if chunks and supplemental:
        chunks.extend(split_section_text("全文补充：\n" + supplemental, max_chars))
    elif not chunks:
        # 部分长条目（如玩家攻略）只有 full_text、没有 sections；必须回退切全文，不能静默丢失。
        chunks = split_section_text(full, max_chars)
    return chunks


def tokenize(text):
    """使用项目专名词典分词，供 BM25 构建和检索保持一致。"""
    return [t for t in jieba.cut(text) if t.strip() and t.strip() != "\n"]


def chunk_records(records, max_chars):
    """把规范化条目切成带稳定 ID、内容哈希和检索前缀的 chunks。"""
    """records → [{id, text, meta, hash}]。chunk id = 分类-item_id-序号。

    text 带条目级元信息前缀（Contextual Retrieval 轻量版）：
    "【分类】名称：正文" —— 让"负山"这类短条目检索时名称能直接命中。
    """
    chunks = []
    for r in records:
        cs = split_chunks(r, max_chars)
        meta = {"item_id": r["item_id"], "name": r["name"],
                "category": r["category"], "chunk_index": 0,
                "chunk_total": len(cs)}
        for key in ("source_kind", "operator_name", "audio_title", "audio_url"):
            value = r.get(key)
            if isinstance(value, (str, int, float, bool)) and value != "":
                meta[key] = value
        for i, c in enumerate(cs):
            meta_i = dict(meta, chunk_index=i)
            # 元信息前缀：分类 + 名称（名称重复 2 次加权，BM25 更易命中名称查询）
            prefixed = f"【{r['category']}】{r['name']}：{r['name']}。{c}"
            chunks.append({
                "id": f"{r['category']}-{r['item_id']}-{i}",
                "text": prefixed,
                "meta": meta_i,
                "hash": r.get("content_hash") or record_content_hash(r),
            })
    return chunks


def write_bm25_shards(chunks, bm25_dir, categories=None):
    """按分类写 BM25 分片；增量模式只传入发生变化的分类。"""
    """按分类写 BM25 分片（bm25/{分类}.pkl）。categories=None 重建全部；否则只重建指定分类。"""
    os.makedirs(bm25_dir, exist_ok=True)
    by_cat = {}
    for c in chunks:
        by_cat.setdefault(c["meta"]["category"], []).append(c)
    if categories is None:
        categories = set(by_cat.keys())
    for cat in sorted(categories):
        ccs = by_cat.get(cat, [])
        shard_path = os.path.join(bm25_dir, f"{cat}.pkl")
        if not ccs:
            if os.path.exists(shard_path):
                os.remove(shard_path)
            continue
        tokenized = [tokenize(c["text"]) for c in ccs]
        bm25 = BM25Okapi(tokenized)
        with open(shard_path, "wb") as f:
            pickle.dump({"bm25": bm25, "chunk_texts": [c["text"] for c in ccs],
                         "metas": [c["meta"] for c in ccs]}, f)
    return by_cat


def inconsistent_bm25_categories(chunks, bm25_dir):
    """找出缺失、陈旧、损坏或多余的 BM25 分类分片。"""
    """找出与最新 manifest 不一致、缺失或损坏的 BM25 分类分片。"""
    expected = {}
    for c in chunks:
        m = c["meta"]
        expected.setdefault(m["category"], set()).add((str(m["item_id"]), int(m["chunk_index"])))
    existing = set()
    broken = set()
    if os.path.isdir(bm25_dir):
        for path in glob.glob(os.path.join(bm25_dir, "*.pkl")):
            cat = os.path.splitext(os.path.basename(path))[0]
            existing.add(cat)
            try:
                with open(path, "rb") as f:
                    data = pickle.load(f)
                actual = {(str(m["item_id"]), int(m["chunk_index"])) for m in data.get("metas", [])}
                if actual != expected.get(cat, set()):
                    broken.add(cat)
            except (OSError, ValueError, KeyError, TypeError, pickle.UnpicklingError):
                broken.add(cat)
    return broken | (set(expected) - existing) | (existing - set(expected))


def main():
    """构建或增量更新向量索引、BM25 分片和 manifest。"""
    import argparse

    ap = argparse.ArgumentParser(description="构建/增量更新 RAG 索引（ChromaDB + BM25 分片）")
    ap.add_argument("--inputs", nargs="*", default=["endfield_kb/*.jsonl"],
                    help="知识库 JSONL（支持 glob），默认 endfield_kb/*.jsonl")
    ap.add_argument("--out-dir", default="output/rag")
    ap.add_argument("--max-chars", type=int, default=512)
    ap.add_argument("--model", default=MODEL_NAME)
    ap.add_argument("--operator-details", default="output/operator_details.json",
                    help="干员详情 JSON（默认把中文语音文本加入索引）")
    ap.add_argument("--no-operator-audio", action="store_true",
                    help="不把干员中文语音文本加入索引")
    ap.add_argument("--reset", action="store_true", help="全量重建（清空 out-dir）")
    ap.add_argument("--incremental", action="store_true", help="增量更新（hash 对比）")
    args = ap.parse_args()

    out_dir = args.out_dir
    if args.reset and os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    os.makedirs(out_dir, exist_ok=True)

    operator_details = None if args.no_operator_audio else args.operator_details
    records = load_records(args.inputs, operator_details_path=operator_details)
    for r in records:
        r["content_hash"] = record_content_hash(r)
    print(f"记录数: {len(records)} 条")

    all_chunks = chunk_records(records, args.max_chars)
    n_single = sum(1 for r in records if len(split_chunks(r, args.max_chars)) == 1)
    manifest_path = os.path.join(out_dir, "chunks.json")

    # ---- 增量/全量差异分析 ----
    changed_ids, deleted_ids, changed_keys, deleted_keys = [], [], [], []
    incremental = args.incremental and os.path.exists(manifest_path)
    if incremental:
        old_manifest = json.load(open(manifest_path, encoding="utf-8"))
        old_entries, old_ids_by_key = {}, {}
        for item in old_manifest:
            k = (item["meta"]["category"], item["meta"]["item_id"])
            old_entries[k] = item["hash"]
            old_ids_by_key.setdefault(k, []).append(item["id"])
        new_entries, new_ids_by_key = {}, {}
        for c in all_chunks:
            k = (c["meta"]["category"], c["meta"]["item_id"])
            new_entries[k] = c["hash"]
            new_ids_by_key.setdefault(k, []).append(c["id"])
        changed_keys = [k for k in new_entries if old_entries.get(k) != new_entries[k]]
        changed_ids = [i for k in changed_keys for i in new_ids_by_key[k]]
        deleted_keys = [k for k in old_entries if k not in new_entries]
        deleted_ids = [i for k in deleted_keys for i in old_ids_by_key[k]]
        print(f"增量: 新增/修改 {len(changed_keys)} 条目（{len(changed_ids)} chunk）| "
              f"删除 {len(deleted_keys)} 条目（{len(deleted_ids)} chunk）")
    else:
        changed_ids = [c["id"] for c in all_chunks]
        print(f"全量: {len(all_chunks)} chunk")

    # ---- embedding（只对变更 chunk）----
    print(f"加载模型 {args.model}（离线）...")
    from sentence_transformers import SentenceTransformer

    model = SentenceTransformer(args.model, local_files_only=True)
    to_embed = [c for c in all_chunks if c["id"] in changed_ids]
    vecs = []
    if to_embed:
        vecs = [v.tolist() for v in model.encode(
            [c["text"] for c in to_embed], batch_size=32,
            show_progress_bar=True, normalize_embeddings=True)]
        print(f"重新 embedding: {len(to_embed)} chunk")
    else:
        print("内容无变化，跳过 embedding")

    # ---- ChromaDB（增量 upsert / delete）----
    import chromadb

    client = chromadb.PersistentClient(path=os.path.join(out_dir, "chroma"))
    coll = client.get_or_create_collection(name="endfield_kb", metadata={"hnsw:space": "cosine"})
    if to_embed:
        # Chroma 的单次批量上限随 SQLite 配置变化；固定小批写入兼容全量大索引。
        upsert_batch = 1000
        for start in range(0, len(to_embed), upsert_batch):
            batch = to_embed[start:start + upsert_batch]
            coll.upsert(ids=[c["id"] for c in batch],
                        embeddings=vecs[start:start + upsert_batch],
                        documents=[c["text"] for c in batch],
                        metadatas=[c["meta"] for c in batch])
    if deleted_ids:
        for start in range(0, len(deleted_ids), 1000):
            coll.delete(ids=deleted_ids[start:start + 1000])
    print(f"ChromaDB: {coll.count()} 条")

    # ---- manifest（全量写最新基线，供下次增量对比）----
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=1)

    # ---- BM25 分片（增量只重建变更分类）----
    bm25_dir = os.path.join(out_dir, "bm25")
    if incremental:
        changed_cats = {k[0] for k in changed_keys} | {k[0] for k in deleted_keys}
        changed_cats |= inconsistent_bm25_categories(all_chunks, bm25_dir)
    else:
        changed_cats = None
    if changed_cats is not None and not changed_cats:
        print("BM25 无变更分类，跳过")
    else:
        write_bm25_shards(all_chunks, bm25_dir, categories=changed_cats)
        print(f"BM25 分片更新: {sorted(changed_cats or {c['meta']['category'] for c in all_chunks})}")

    # ---- 报告 ----
    report = [
        "RAG 索引构建完成",
        f"模式: {'增量' if incremental else '全量'}",
        f"模型: {args.model}",
        f"chunk 总数: {len(all_chunks)}",
        f"整条未拆: {n_single}",
        f"单 chunk 上限: {args.max_chars} 字符",
        f"输出目录: {out_dir}",
    ]
    print("\n".join(report))
    with open(os.path.join(out_dir, "report.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(report))

    # 统一落盘机器可读审计结果，供发布门禁与深度健康检查使用。
    from rag_audit import audit_index
    status = audit_index(out_dir)
    with open(os.path.join(out_dir, "build_status.json"), "w", encoding="utf-8") as f:
        json.dump(status, f, ensure_ascii=False, indent=2)
    if not status["consistent"]:
        print("索引审计警告: " + "; ".join(status["issues"]))


if __name__ == "__main__":
    main()
