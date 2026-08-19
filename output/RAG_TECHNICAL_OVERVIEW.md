# 终末地知识问答 RAG：技术方案、监控与评测审计

> 审计日期：2026-08-19  
> 范围：知识库构建、索引、检索、问答路由、答案生成、监控、评测集与效果判断。  
> 结论原则：**原始 WIKI 是事实源，`endfield_kb` 是规范化数据，RAG 只是可重建的派生检索层，不能把“未召回”解释为“原文不存在”。**

## 1. 执行结论

本项目已经有一套可工作的 RAG/问答技术链路，并非只有“向量库 + LLM”：

- 有 1958 条、22 分类的规范化知识库；
- 有 3402 个 chunk、ChromaDB 向量索引、按分类分片的 BM25 和 manifest；
- 有条目 hash 驱动的增量更新和 BM25 分片一致性自愈；
- 有规则/LLM 意图识别、结构化配方直查、分类枚举、实体全文直取、向量/BM25/名称/关键词/mention 多路检索；
- 有带来源引用的 LLM 答案生成和低相关拒答；
- 有 71 条、覆盖 5 类意图和 3 档难度的离线检索评测集；
- 有多轮历史评测结果，当前候选检索 Recall@5=100%、MRR=97.3%。

但目前不能称为“完整可观测、完整评测的生产级 RAG”。主要缺口是：

- `/api/health` 只检查进程存活，不检查索引、BM25、embedding、LLM 或数据新鲜度；
- 没有请求级延迟、错误率、路由分布、检索空结果率和 LLM 降级率统计；
- 100% Recall 是候选检索评测，不是 `/api/ask` 端到端成功率；
- 没有正式的意图分类准确率报告；
- 没有答案忠实度、完整性、引用正确性和拒答正确率的落盘评测；
- 没有 RAGAS/LLM-as-judge 或稳定的人工答案评分集；
- 评测没有接入 CI，也没有阈值失败门禁和指标回退报警；
- reranker 仍是规划项，当前未实现。

## 2. 当前整体技术链路

```text
原始 WIKI JSON（事实源，约 147MB / 1958 条）
  │
  ├─ build_kb_all.py
  │    └─ endfield_kb/*.jsonl + *.md + _catalog.json
  │       （22 分类，保留正文、表格和结构块）
  │
  ├─ recipe_extract.py
  │    └─ output/recipes.json（345 个精确配方）
  │
  └─ extract_media.py
       └─ output/item_media.json（封面、图片、引用）

endfield_kb/*.jsonl
  │
  └─ build_rag.py
       ├─ chunk：条目名称/分类元信息前缀 + 正文，最大 512 字符
       ├─ embedding：BAAI/bge-small-zh-v1.5，离线加载
       ├─ ChromaDB：余弦向量检索
       ├─ BM25：jieba + 游戏专名词典，按分类分片
       ├─ chunks.json：chunk 清单、meta、content_hash
       └─ report.txt：构建模式、模型、chunk 数等摘要

用户问题
  │
  ├─ 意图识别：L1 规则；规则未命中时可用 LLM 兜底
  │
  └─ rag_ask.ask()
       ├─ 枚举问题 → 按分类/名称确定性枚举
       ├─ 配方/设备 → recipes.json 结构化直查
       ├─ 明确实体 → 读取完整知识库条目
       └─ 开放问题 → 多路检索
            ├─ 向量召回
            ├─ BM25 召回
            ├─ 条目名称召回
            ├─ 全文关键词召回
            ├─ mention 反查
            └─ 可选 LLM 查询改写
                 ↓
              去重和规则排序
                 ↓
              top-k 上下文
                 ↓
              LLM 生成带 [来源N] 的回答
```

### 2.1 为什么不是所有问题都走 RAG

项目采用“确定性优先、相似检索兜底”：

| 问题类型 | 当前策略 | 原因 |
|---|---|---|
| “重息壤怎么合成” | `recipes.json` 直查 | 配方是结构化事实，不应让语义模型猜 |
| “主线任务有哪些” | 分类枚举 | 枚举要求完整集合，top-k 天生会漏 |
| “诀升满级要什么” | 实体全文直取 | 已确认实体时，完整原文比 chunk 排序更可靠 |
| “解锁武陵需要什么条件” | 多路检索 | 信息跨条目、间接出现，需要组合线索 |
| 普通知识介绍 | 混合检索 | 适合语义和关键词共同召回 |

这种路由是当前方案最重要的部分。系统不是“所有问题一锅 RAG”，而是只把开放问题交给相似性检索。

## 3. 数据与索引可靠性

### 3.1 已实现

1. **事实源与派生索引分离**  
   原始 JSON 和 `endfield_kb` 是可检查数据；Chroma/BM25 可以删除后重建。

2. **条目级内容 hash**  
   `build_rag.py` 对 `full_text` 计算 MD5。增量更新比较新旧 hash，只重新 embedding 变化条目，并删除已消失条目。

3. **manifest**  
   `output/rag/chunks.json` 保存全部 chunk、来源 meta 和 hash，能够审计“某条目是否进入索引”。

4. **BM25 分类分片**  
   更新时只重建发生变化的分类，减少全量成本。

5. **分片一致性自愈**  
   `inconsistent_bm25_categories()` 会发现缺失、陈旧、损坏或多余的 BM25 分片，并在增量构建时重建对应分类。

6. **长条目漏索引修复**  
   若条目 `sections` 为空，切块逻辑回退到 `full_text`。该修复恢复了 53 个漏索引条目和 370 个 chunk。

7. **构建摘要**  
   当前 `output/rag/report.txt` 记录：增量模式、模型 `BAAI/bge-small-zh-v1.5`、3402 chunks、512 字符上限等。

### 3.2 尚未实现

- manifest 没有统一的构建时间、原始数据文件指纹、代码版本和 schema 版本；
- 构建报告没有记录新增/修改/删除条目数的历史序列；
- 没有独立命令一次性核对：知识库条目数、manifest 条目数、Chroma count、BM25 chunk 键是否全部一致；
- 服务启动时不会验证索引是否完整、是否比知识库陈旧；
- mention 索引不是统一构建管线的一部分，知识库更新后可能忘记重建；
- 没有数据漂移、索引陈旧或异常 chunk 数变化报警。

## 4. 检索方案

### 4.1 第一阶段混合检索

`scripts/rag_search.py` 当前包含三路候选：

- `vector_search()`：embedding 语义召回；
- `bm25_search()`：精确词项与专有名词召回；
- `name_search()`：名称核心词与攻略/视频意图增强。

三路结果通过 RRF 融合。默认参数为：

```text
最终 top_k = 5
BM25 候选 = 20
向量候选 = 20
RRF k = 60
```

### 4.2 问答层的补充检索

`scripts/rag_ask.py` 对开放问题增加：

- 查询改写：把模糊问题拆成最多 3 个子查询；
- 全文关键词：在条目名和全文中匹配，并按任务/活动等分类加权；
- mention 反查：寻找“哪些条目提到了这个实体/地点”；
- 实体增强：明确条目时直接取全文；
- 规则合并：人工确认性质更强的 direct/keyword/mention 结果优先。

### 4.3 rerank 状态

规划文档曾设计 cross-encoder reranker，但代码中没有实现。当前决定是先保留为可选项，因为名称召回和漏索引修复后，现有 71 条检索集已经达到 Recall@5=100%。

是否引入 rerank 不能只看当前 71 条，应先增加真实复杂问题和 hard negatives；只有它显著改善首位排序、引用准确率或答案完整性，且延迟可接受，才值得增加这个新系统。

## 5. 答案生成与可信边界

已实现：

- top-k 资料拼接成带来源编号的上下文；
- system prompt 要求只基于资料回答；
- 输出中使用 `[来源N]`；
- 普通向量结果 top-1 相似度低于阈值时拒答；
- direct/keyword/mention 等人工规则确认的上下文不被向量阈值误拒；
- LLM 未配置或调用失败时安全降级，不导致 API 崩溃。

尚未实现：

- 没有程序验证回答中的 `[来源N]` 是否存在；
- 没有验证每个事实是否真的被对应来源支持；
- 没有区分“检索为空、LLM 超时、鉴权失败、额度不足、模型输出为空”等失败原因给监控层；
- `gen_answer()` 捕获异常后返回 `None`，当前不保留脱敏错误类别和耗时；
- 没有多轮对话状态和代词消解；
- 没有端到端答案评测门禁。

## 6. 当前监控能力审计

### 6.1 已有的离线监控/自检

| 能力 | 状态 | 位置 |
|---|---|---|
| 条目内容变化检测 | 已实现 | `content_hash` |
| manifest 审计基础 | 已实现 | `output/rag/chunks.json` |
| BM25 分片一致性检查 | 已实现 | `inconsistent_bm25_categories()` |
| 分片自动修复 | 已实现 | 增量构建流程 |
| 构建摘要 | 已实现但较简单 | `output/rag/report.txt` |
| 漏索引回归测试 | 已实现 | `tests/test_build_rag.py` |
| 名称召回回归测试 | 已实现（3 个重点样本） | `tests/test_rag_search.py` |
| API 存活检查 | 已实现 | `GET /api/health` |

### 6.2 缺少的线上可观测性

| 能力 | 当前状态 | 建议指标 |
|---|---|---|
| 深度健康检查 | 未实现 | manifest/chroma/BM25/embedding/LLM 分项状态 |
| 请求量和成功率 | 未实现 | `ask_requests_total`、`ask_success_rate` |
| 路由分布 | 未实现 | enum/structured/direct/rag 占比 |
| 检索质量代理指标 | 未实现 | 空结果率、低分拒答率、top-1/top-5 分数 |
| LLM 稳定性 | 未实现 | 超时率、4xx/5xx、降级率、空回答率 |
| 延迟 | 未实现 | 分类、检索、改写、生成、总耗时 p50/p95 |
| 数据新鲜度 | 未实现 | 源数据时间、索引时间、索引落后时长 |
| 引用质量 | 未实现 | 无效引用率、无引用回答率、来源覆盖率 |
| 用户反馈 | 未实现 | 有用/无用、原因标签、修正样本沉淀 |
| 报警 | 未实现 | 指标阈值异常时写日志/通知 |

因此目前更准确的表述是：**具备离线构建自检，没有完整的运行时监控系统。**

## 7. 评测集与效果评判

### 7.1 已有评测集

`output/eval/eval_set.jsonl` 当前有 71 条，字段包括：

```json
{
  "query": "用户问题",
  "intent": "配方/设备/知识/比较/数值",
  "difficulty": "简单/中等/困难",
  "gold_names": ["正确条目名称"],
  "relevance": 2,
  "anchor": {},
  "core": "核心实体",
  "source": "生成或校验来源"
}
```

分布：

- 意图：配方 16、设备 17、知识 12、数值 14、比较 12；
- 难度：简单 30、中等 22、困难 19。

评测集由 `gen_eval_set.py` 按意图和难度生成。配方/设备类可用 `recipes.json` 交叉核对；部分知识问题和 gold 经过人工审计，但还不是全面双人标注的数据集。

### 7.2 已实现指标

`eval_retrieval.py` 当前计算：

- Recall@k：top-k 是否至少命中 gold；
- MRR：第一个正确条目的排名；
- Precision@k：top-k 中 gold 名称命中的比例近似值；
- 按“意图 × 难度”分组报告；
- 比较类要求两个目标都命中。

未实现 NDCG，虽然早期计划中曾列出。

### 7.3 历史结果

| 版本 | 样本数 | Recall@5 | MRR | Precision@5 |
|---|---:|---:|---:|---:|
| baseline | 79 | 72.15% | 79.75% | 24.81% |
| 词典 + 元信息 | 79 | 84.81% | 92.83% | 37.47% |
| final_reviewed | 71 | 100% | 97.30% | 42.25% |

注意：基线与最终版样本数不同，最终版还包含 gold 人工修正，因此这些数字可用于追踪迭代，但不是完全严格的同集合 A/B 实验。

### 7.4 100% 指标的准确含义

`eval_retrieval.py` 直接调用 `RAGRetriever.search()`，所以最终指标只证明：

> 在这 71 个问题上，正确名称出现在第一阶段检索 top-5 中，并且通常排名较前。

它没有证明：

- 意图识别一定正确；
- `rag_ask.ask()` 选了正确路由；
- 枚举结果完整；
- 多路检索找齐了全部前置条件；
- LLM 没有遗漏或编造；
- `[来源N]` 引用支持对应表述；
- 拒答判断正确；
- 在线调用稳定且延迟可接受。

因此不能把 Recall@5=100% 表述为“问答准确率 100%”。

### 7.5 尚缺的评测层

1. **意图/路由评测**  
   指标：intent accuracy、route accuracy、结构化直查命中率、错误路由成本。

2. **上下文质量评测**  
   指标：Context Recall、Context Precision、证据覆盖率、多跳事实是否全部出现。

3. **答案质量评测**  
   建议人工 0-2 分标注：忠实度、完整性、相关性、引用正确性、表达清晰度。

4. **拒答评测**  
   同时准备有答案和无答案问题，计算正确拒答率、错误拒答率、幻觉率。

5. **运行性能评测**  
   记录 p50/p95 延迟、LLM 失败率、单问题 token/费用、无 LLM 降级表现。

6. **数据完整性评测**  
   随机抽取原始条目，对照 `endfield_kb`、manifest、Chroma 和 BM25，验证全链路可追溯。

7. **真实用户问题集**  
   将真实失败问题脱敏后沉淀为 hard cases，而不是只使用自动生成问题。

## 8. 推荐的生产化监控方案

### 8.1 构建阶段门禁

每次全量或增量更新后自动生成机器可读 `build_status.json`：

```json
{
  "schema_version": 1,
  "source_fingerprint": "...",
  "built_at": "...",
  "git_commit": "...",
  "embedding_model": "BAAI/bge-small-zh-v1.5",
  "kb_entries": 1958,
  "manifest_chunks": 3402,
  "chroma_chunks": 3402,
  "bm25_chunks": 3402,
  "mention_index_entries": 1708,
  "consistent": true
}
```

门禁条件：计数一致、无损坏分片、无异常骤降、评测指标不低于基线。失败时不替换上一个可用索引。

### 8.2 运行时深度健康检查

保留轻量 `/api/health`，新增仅供维护的 `/api/health/deep`：

```text
API process       ok/fail
manifest readable ok/fail
Chroma count      expected/actual
BM25 shards       expected/missing/corrupt
embedding model   cached/missing
LLM config        configured/not-configured
LLM probe         可选，避免每次健康检查产生费用
index age         hours
```

### 8.3 请求级可观测性

为每次 `/api/ask` 生成 `trace_id`，记录脱敏结构日志：

```json
{
  "trace_id": "...",
  "intent": "知识",
  "intent_method": "rule",
  "route_used": "rag",
  "retrieval_count": 5,
  "top_score": 0.63,
  "had_direct": false,
  "had_keyword": true,
  "retrieval_ms": 120,
  "generation_ms": 2400,
  "total_ms": 2580,
  "answer_generated": true,
  "rejected": false,
  "error_type": null
}
```

默认不记录 API key；用户原问题是否落盘应做可配置开关，并考虑隐私。

### 8.4 质量回归门禁

建议每次索引或检索代码变化后执行：

```text
数据一致性检查
  ↓
71 条固定检索回归集
  ↓
路由评测集
  ↓
20~50 条答案黄金集（可选择是否调用在线 LLM）
  ↓
与上一基线比较
  ↓
任一关键指标下降超过阈值则阻止发布
```

建议最低门槛不是永远要求 100%，而是：固定集无回退、新增真实失败样本逐步扩大、各意图和困难档单独达标。

## 9. 推荐评测集体系

不要把所有测试混在一个 JSONL 中，建议拆成五层：

```text
output/eval/
├─ retrieval_gold.jsonl       # 名称/条目召回
├─ routing_gold.jsonl         # 意图与 route_used
├─ context_gold.jsonl         # 回答必须具备的证据点
├─ answer_gold.jsonl          # 参考答案、引用和人工评分
├─ abstention_gold.jsonl      # 无答案、歧义、诱导幻觉问题
└─ hard_cases.jsonl           # 真实线上失败样本
```

答案评测样本建议包含：

```json
{
  "query": "解锁武陵需要满足什么条件？",
  "expected_route": "rag",
  "required_facts": [
    "完成第一章对应前置任务",
    "进入第二章初探武陵任务链"
  ],
  "acceptable_sources": ["对应任务条目A", "对应任务条目B"],
  "should_refuse": false,
  "notes": "明确事实与推断路径必须分开表达"
}
```

人工评分建议每项 0/1/2：

| 维度 | 0 | 1 | 2 |
|---|---|---|---|
| 忠实度 | 有资料外编造 | 部分表述无证据 | 全部有证据 |
| 完整性 | 缺关键事实 | 覆盖部分 | 覆盖全部 required facts |
| 引用正确性 | 引用错误 | 部分对应 | 每项关键事实均可追溯 |
| 相关性 | 答非所问 | 有冗余/偏题 | 直接回答 |
| 拒答 | 错误回答/错误拒答 | 边界含糊 | 判断正确且说明原因 |

## 10. 分阶段改进路线

### P0：先解决“黑箱不可诊断”

1. 新增独立索引审计命令，核对 KB/manifest/Chroma/BM25/mention；
2. 构建产出 `build_status.json`，包含版本、时间和全链路计数；
3. `/api/ask` 返回或日志记录安全的 `trace_id`、route、耗时和失败类别；
4. 将 LLM 异常从静默 `None` 改为内部可观测的脱敏错误类型；
5. 提供从 hit 的 item_id 回读完整原始条目的能力。

### P1：补齐端到端评测

1. 从现有 71 条中建立独立 routing gold；
2. 人工制作 20~50 条答案黄金集；
3. 加入无答案、歧义和提示注入样本；
4. 评测 `/api/ask` 而不只是 `RAGRetriever.search()`；
5. 记录忠实度、完整性、引用正确性、拒答和延迟。

### P2：再决定是否引入 rerank

1. 扩充困难比较、多跳、同名和高相似 hard negatives；
2. 保存无 rerank 基线；
3. 对比 rerank 后 MRR、Context Precision、答案引用正确率和 p95 延迟；
4. 只有质量提升明显且运行成本可接受才启用；
5. 必须保留原始召回结果和 rerank 分数，避免形成新的不可诊断黑箱。

### P3：持续运营

- 将真实失败案例回流到 `hard_cases.jsonl`；
- 每次 WIKI 更新执行增量构建、完整性审计和固定集回归；
- 保存趋势而不只保存最后一个结果；
- 对空结果率、错误拒答率、LLM 降级率和索引年龄设置阈值。

## 11. 最终技术判断

当前系统的强项是：数据真实、结构化配方优先、检索路由不是一锅炖、索引可增量更新、候选召回已经经过评测和一次真实漏索引审计。

当前系统的弱项是：运行时可观测性和端到端答案评测不足，现有优秀指标容易被误读成整体问答准确率。

后续最优先的工作不是立刻换 embedding 或添加 reranker，而是先让系统做到：

1. 能证明原始数据确实进入了每一层索引；
2. 能解释一次问题走了什么路由、拿到了什么证据、在哪一步失败；
3. 能分别衡量召回、上下文和最终答案；
4. 在 RAG 不可靠时允许回读完整原始条目验证。

做到这些以后，RAG 才是“高可信、可审计的加速层”，而不是 Agent 无法检查的事实黑箱。
