# 数据管道

## 数据分层

| 层级 | 位置 | 可否修改 | 用途 |
|---|---|---:|---|
| 原始事实 | `endfield_wiki_full_*.json` 等 | 否 | WIKI 块式文档快照 |
| 规范化知识 | `endfield_kb/` | 由脚本生成 | 22 个分类的 JSONL 与 Markdown |
| 结构化产物 | `output/recipes.json`、`item_media.json`、`operator_details.json` | 由脚本生成 | 配方、媒体和干员详情 |
| 检索产物 | `output/rag/`、`mention_index.json`、`knowledge_graph/graph.db` | 由脚本生成 | 在线检索与关系查询 |
| 评测产物 | `output/eval/` | 由评测工具生成 | 回归基线和版本证据 |

## 构建流程

```powershell
python scripts/build_kb_all.py
python scripts/recipe_extract.py
python scripts/extract_media.py
python scripts/build_operator_details.py
python scripts/build_rag.py --inputs "endfield_kb/*.jsonl" --reset
python scripts/build_knowledge_graph.py
```

全量和增量的精确参数以脚本 `--help` 与 [TOOLS.md](TOOLS.md) 为准。mention 索引的当前生成入口也应从工具清单确认，避免新建重复脚本。

## 解析与一致性规则

- `build_kb_all.py` 保留 `item_id`、名称、分类、`sections`、`sections_struct` 和 `full_text`；表格、引用、图片和数量不能静默丢失；
- `recipe_extract.py` 保留 345 条已提取真实配方，包括设备制造、盛装、矿机和原木；循环在展示层剪枝；
- RAG 条目哈希覆盖正文、章节和索引策略；增量更新按实际新旧 chunk ID 差集删除遗留向量；
- embedding 模型变化必须使用新输出目录或全量重建，避免不同向量共存；
- BM25 分片和 manifest 原子替换，构建结束必须核对 manifest、Chroma 与分片键；
- 图谱按来源哈希先删旧派生关系再重建，实体使用 UPSERT 保持关系完整。

## 常见问题与对策

| 问题 | 对策 |
|---|---|
| `sections` 为空导致长条目漏索引 | 回退切分 `full_text` |
| `sections` 未覆盖描述或“其他内容” | 对照全文补充未覆盖内容 |
| 中文专名被 jieba 拆碎 | 用 `gen_jieba_dict.py` 生成并加载项目词典 |
| 条目缩短后旧 chunk 残留 | 比较完整新旧 chunk 集合并删除差集 |
| 服务占用 Chroma 文件 | 重建前停止服务或在独立目录构建 |
| 中文终端乱码 | 将结果写入 UTF-8 文件后读取 |

## 预留扩展点

- 为所有产物增加统一 `schema_version`、`built_at`、来源指纹和构建参数；
- 在独立版本目录完成索引构建与审计后切换活动版本，保留上一版快速回滚；
- 用稳定 `item_id` 贯穿配方、知识库、图谱和客户端，减少名称歧义；
- 对数据源新增适配器时先输出同一规范化 schema，避免下游感知采集格式。
