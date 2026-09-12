# 整体架构

## 产品边界

系统由两条互补能力组成：配方查询使用结构化数据确定性生成合成树；知识问答使用结构化直查、知识图谱与文本检索协作。Web 和微信小程序只是两种客户端，共用同一个 FastAPI 后端。

```text
官方 WIKI JSON（只读事实源）
  ├─ 规范化知识库 ──► RAG 索引 / mention 索引 / 知识图谱
  ├─ 配方提取 ──────► recipes.json
  └─ 媒体与干员提取 ► item_media.json / operator_details.json

Web / 微信小程序
  └─ FastAPI
       ├─ 配方与详情：recipes + KB + media
       └─ 知识问答：确定性路由 → graph/RAG → 有证据的可选 LLM 生成
```

## 模块职责

| 层 | 位置 | 职责 |
|---|---|---|
| 事实源 | 根目录历史 JSON | 保存采集结果，只读 |
| 构建 | `scripts/build_*.py`、`recipe_extract.py` | 生成可重建的数据与索引 |
| 领域逻辑 | `recipe_index.py`、`rag_ask.py`、`graph_search.py` | 名称解析、树生成、问答编排和图查询 |
| 服务 | `scripts/api_server.py` | 输入校验、限额、并发、SSE、媒体代理、静态托管 |
| 客户端 | `web/`、`miniprogram/` | 搜索、结果、媒体和反馈交互；Web 另有与业务数据隔离的按需 3D 展示层 |
| 质量 | `tests/`、`scripts/eval_*.py`、`quality_gate.py` | 回归、指标、审计和发布门禁 |
| 运维 | Dockerfile、Compose、`deploy/` | 离线镜像、反向代理、安全和回滚 |

## 技术选型与理由

| 选择 | 未采用 | 理由 |
|---|---|---|
| FastAPI + Pydantic v2 | Flask / Django | 一个服务同时提供 API、SSE 与静态托管；Pydantic 承担边界校验；同步端点在 threadpool 执行，天然适配阻塞式检索与 LLM 调用 |
| React 18 + TypeScript + Vite 6；Three.js 按需加载 | 单文件 HTML / 全站 WebGL | 前后端字段契约需要类型约束；DOM 保持可访问内容，Three.js 只承担环境与展示载体，构建产物仍由后端托管 |
| Web 用 React SVG，小程序用 Canvas | 两端共用一套渲染 | 触控、像素比与渲染模型差异大，只共享数据契约、名称规则和业务不变量（ADR-10） |
| ChromaDB（进程内嵌入式） | Milvus / Weaviate / pgvector | 索引约 7 千 chunk、单机部署，需要零运维和"可删除重建"；嵌入式库最匹配 |
| BM25（rank-bm25）+ 向量 + 名称/mention 多路召回，RRF 融合 | 只用向量检索 | 游戏专名与短名称必须字面命中；RRF 规避不同检索器分数不可比（ADR-13） |
| `bge-small-zh-v1.5` 离线 CPU 推理 | 在线 embedding API / 更大模型 | 中文语料、CPU 可跑，运行时 embedding 与索引读取不联网且无按量费用；生成式回答仍会调用已配置的在线 LLM（ADR-12） |
| SQLite（图谱、Trace、额度计数） | Neo4j 等图数据库 / Redis | 实体约 2 千、关系约 9 千，单机读写；需要单文件审计、可重建、零外部服务（ADR-15） |
| SSE 流式 | WebSocket / 轮询 | 只需服务端单向推送，可复用现有 HTTP 准入、限流与反向代理链路（ADR-05） |
| 轻量自研编排 | LangChain / LlamaIndex / GraphRAG 框架 | 路由与证据链必须确定性、可审计；框架会隐藏控制流并引入不可控依赖（ADR-16） |
| unittest + Vitest + node:test | 统一到单一测试框架 | 后端零额外依赖，前端需要 DOM 环境，小程序只能跑 Node 断言；全部离线、不调用付费模型 |
| Docker 多阶段构建，构建期重建索引 | 运行期下载 embedding 或重建索引 | 运行时不访问 Hugging Face，镜像自带模型和完整索引；仓库忽略 Chroma 与模型缓存，但仍跟踪必要的 BM25、manifest 和评测产物（ADR-09） |

## 明确不做的范围

- 不做开放式 Agent Loop：确定性工具配确定性调度，模型不负责反复选工具（ADR-02、[EXTENSIBILITY.md](EXTENSIBILITY.md)）；
- 不让 LLM 写正式知识库或图谱，也不用 RAG 推测配方数值；
- 不做多租户、多主机分布式限流和跨主机共享额度（当前是单主机单副本定位）；
- 不把"图里没有路径"表述成"现实中不存在该关系"；
- 不在缺少困难评测证据时引入 reranker、补检索循环或更大模型。
- 不让 3D 档案载体承载或猜测知识事实；配方与问答内容始终由现有 DOM 和数据链呈现。

## 在线请求边界

- `/api/synthesis` 只从真实配方和规范化知识库取事实；
- `/api/ask` 与 `/api/ask/stream` 共用问答编排，区别只是答案传输方式；
- 结构化直查可为 0 次 LLM；普通开放问题通常需要语义规划和回答生成各一次；
- `LLM_TOTAL_TIMEOUT` 约束一次客户端操作及其重试、续写，不是整个问答请求的统一截止时间；
- Web 流式请求可主动停止并在断开时终止生成；小程序当前使用 180 秒整包问答，取消和统一请求预算仍是扩展项。

## 设计原则

1. 事实准确和可追溯优先于自然表达；
2. 能确定性回答的内容不交给模型猜；
3. 原始数据不可变，派生产物可重建；
4. 失败必须可见，并保留超时、上限、降级和审计路径；
5. 新复杂度必须在固定评测或真实困难样本上证明收益。

数据细节见 [DATA_PIPELINE.md](DATA_PIPELINE.md)，各能力分别见 [SYNTHESIS.md](SYNTHESIS.md)、[RAG.md](RAG.md)、[GRAPH.md](GRAPH.md) 和 [API.md](API.md)；
验证方式见 [TESTING.md](TESTING.md)，选型取舍见 [DECISIONS.md](DECISIONS.md)，预留能力见 [EXTENSIBILITY.md](EXTENSIBILITY.md)。
