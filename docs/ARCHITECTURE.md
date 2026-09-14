# 整体架构

系统由两条互补能力组成：配方查询使用结构化数据确定性生成合成树；知识问答由结构化直查、知识图谱与文本检索协作完成。Web 和微信小程序只是两种客户端，共用同一个 FastAPI 后端。

```text
官方 WIKI JSON（只读事实源）
  ├─ 规范化知识库 ──► RAG 索引 / mention 索引 / 知识图谱
  ├─ 配方提取 ──────► recipes.json
  └─ 媒体与干员提取 ► item_media.json / operator_details.json

Web / 微信小程序 ──► FastAPI
  ├─ 配方与详情：recipes + KB + media
  └─ 知识问答：确定性路由 → graph/RAG → 有证据的可选 LLM 生成
```

## 1. 模块关系

| 层 | 位置 | 职责 |
|---|---|---|
| 事实源 | 根目录历史 JSON | 保存采集结果，只读 |
| 构建 | `scripts/build_*.py`、`recipe_extract.py` | 生成可重建的数据与索引 |
| 领域逻辑 | `recipe_index.py`、`rag_ask.py`、`graph_search.py` | 名称解析、树生成、问答编排和图查询 |
| 服务 | `scripts/api_server.py` | 输入校验、限额、并发、SSE、媒体代理、静态托管 |
| 客户端 | `web/`、`miniprogram/` | 搜索、结果、媒体和反馈交互；Web 另有与业务数据隔离的按需 3D 展示层 |
| 质量与运维 | `tests/`、`scripts/eval_*.py`、`quality_gate.py`、Dockerfile、`deploy/` | 回归、指标、审计、发布门禁和离线部署 |

设计原则：事实准确和可追溯优先于自然表达；能确定性回答的内容不交给模型猜；原始数据不可变、派生产物可重建；失败必须可见并保留超时、上限、降级和审计路径；新复杂度必须在固定评测或真实困难样本上证明收益。

在线请求边界：

- `/api/synthesis` 只从真实配方和规范化知识库取事实；
- `/api/ask` 与 `/api/ask/stream` 共用问答编排，区别只是答案传输方式；
- 结构化直查可为 0 次 LLM；普通开放问题通常需要语义规划和回答生成各一次；
- `LLM_TOTAL_TIMEOUT` 约束一次客户端操作及其重试、续写，不是整个问答请求的统一截止时间；
- Web 流式请求可主动停止并在断开时终止生成；小程序当前使用 180 秒整包问答，取消和统一请求预算仍是扩展项。

## 2. 技术选型总览

| 选择 | 未采用 | 理由 |
|---|---|---|
| FastAPI + Pydantic v2 | Flask / Django | 一个服务同时提供 API、SSE 与静态托管；Pydantic 承担边界校验；同步端点在 threadpool 执行，适配阻塞式检索与 LLM 调用 |
| React 18 + TypeScript + Vite 6；Three.js 按需加载 | 单文件 HTML / 全站 WebGL | 前后端字段契约需要类型约束；DOM 保持可访问内容，Three.js 只承担环境与展示载体，构建产物仍由后端托管 |
| Web 用 React SVG，小程序用 Canvas | 两端共用一套渲染 | 触控、像素比与渲染模型差异大，只共享数据契约、名称规则和业务不变量（ADR-10） |
| ChromaDB（进程内嵌入式） | Milvus / Weaviate / pgvector | 索引 8,300 chunk、单机部署，需要零运维和"可删除重建"；嵌入式库最匹配 |
| BM25（rank-bm25）+ 向量 + 名称/mention 多路召回，RRF 融合 | 只用向量检索 | 游戏专名与短名称必须字面命中；RRF 规避不同检索器分数不可比（ADR-13） |
| `bge-small-zh-v1.5` 离线 CPU 推理 | 在线 embedding API / 更大模型 | 中文语料、CPU 可跑，运行时 embedding 与索引读取不联网且无按量费用；生成式回答仍调用已配置的在线 LLM（ADR-12） |
| SQLite（图谱、Trace、额度计数） | Neo4j 等图数据库 / Redis | 2,405 个实体、10,076 条关系，单机读写；需要单文件审计、可重建、零外部服务（ADR-15） |
| SSE 流式 | WebSocket / 轮询 | 只需服务端单向推送，可复用现有 HTTP 准入、限流与反向代理链路（ADR-05） |
| 轻量自研编排 | LangChain / LlamaIndex / GraphRAG 框架 | 路由与证据链必须确定性、可审计；框架会隐藏控制流并引入不可控依赖（ADR-16） |
| unittest + Vitest + node:test | 统一到单一测试框架 | 后端零额外依赖，前端需要 DOM 环境，小程序只能跑 Node 断言；全部离线、不调用付费模型 |
| Docker 多阶段构建，构建期重建索引 | 运行期下载 embedding 或重建索引 | 运行时不访问 Hugging Face，镜像自带模型和完整索引；仓库忽略 Chroma 与模型缓存，但仍跟踪必要的 BM25、manifest 和评测产物（ADR-09） |

## 3. 数据流与分层

| 层级 | 位置 | 可否修改 | 用途 |
|---|---|---:|---|
| 原始事实 | `endfield_wiki_full_*.json` 等 | 否 | WIKI 块式文档快照 |
| 规范化知识 | `endfield_kb/` | 由脚本生成 | 22 个分类的 JSONL 与 Markdown |
| 结构化产物 | `output/recipes.json`、`item_media.json`、`operator_details.json` | 由脚本生成 | 配方、媒体和干员详情 |
| 检索产物 | `output/rag/`、`output/mention_index.json`、`output/knowledge_graph/graph.db` | 由脚本生成 | 在线检索与关系查询 |
| 评测产物 | `output/eval/` | 由评测工具生成 | 回归基线和版本证据 |

## 4. 业务不变量

1. 配方树唯一事实源是 `output/recipes.json`，不得用 RAG 猜配方；
2. 叶子必须收敛到基础资源：清水、惰气、息壤气、无产出配方矿物或种子类；
3. 每个物品最多展示 2 个配方，必须处理自循环并把最大深度限制为 10；
4. 名称歧义返回候选，不自动猜测；无配方物品回退知识库详情；
5. 配方提取保留完整真实记录，展示规则不反向清洗事实数据；
6. 知识图谱的确定关系必须带来源和证据；图未命中不能解释为关系不存在；
7. LLM 只根据检索证据生成，不能直接修改正式知识库或图谱。

## 5. 数据构建流程

```powershell
python scripts/diff_wiki_snapshots.py OLD.json NEW.json --out output/update_YYYYMMDD/wiki_delta.json
python scripts/build_kb_all.py
python scripts/recipe_extract.py
python scripts/extract_media.py
python scripts/build_operator_details.py
python scripts/build_rag.py --inputs "endfield_kb/*.jsonl" --reset
python scripts/build_knowledge_graph.py
```

- 全量和增量的精确参数以脚本 `--help` 与 [DEVELOPMENT.md](DEVELOPMENT.md) 的工具清单为准；mention 索引的当前生成入口也从工具清单确认，避免新建重复脚本；
- 轮次产物按日期归档到 `output/update_YYYYMMDD/`，不要写到 `output/` 根目录造成版本混淆；该目录是本机的过程产物与回滚材料，体积可达数百 MB，已被 `.gitignore` 的 `output/update_*/` 忽略。

## 6. 解析与一致性规则

- `build_kb_all.py` 保留 `item_id`、名称、分类、`sections`、`sections_struct` 和 `full_text`；表格、引用、图片和数量不能静默丢失；
- 新快照进入正式构建前必须校验目录/详情计数、详情成功率和稳定 ID 唯一性，并保存增删改差分；
- `recipe_extract.py` 保留 345 条已提取真实配方，包括设备制造、盛装、矿机和原木；循环在展示层剪枝；
- RAG 条目哈希覆盖正文、章节和索引策略；增量更新按实际新旧 chunk ID 差集删除遗留向量；
- embedding 模型变化必须使用新输出目录或全量重建，避免不同向量共存；
- BM25 分片和 manifest 原子替换，构建结束必须核对 manifest、Chroma 与分片键；
- 图谱按来源哈希先删旧派生关系再重建；来源下线时删除实体并重建依赖来源；实体使用 UPSERT 保持关系完整；
- mention 缓存以规范化知识源指纹判定新鲜度，不能只检查文件是否存在；
- 中文专名被 jieba 拆碎时用 `gen_jieba_dict.py` 生成并加载项目词典；服务占用 Chroma 文件时先停服或在独立目录构建。

## 7. 配方合成树

- 配方树是确定性领域能力：数据来自 `output/recipes.json`，索引工具是 `scripts/recipe_index.py`，服务入口与递归树构建在 `scripts/api_server.py`；Web 用 React 递归 SVG，小程序用 Canvas，两端共享响应数据与业务不变量，各自实现渲染和手势；
- 选择结构化配方而非 RAG，是因为原料、数量、设备和耗时必须精确；选择 SVG/Canvas，是为了直接控制节点、连线、缩放与移动端交互，无需维护已弃用的 D3 依赖；
- 小样例容易漏掉真实数据中的循环和异常配方，因此测试必须遍历全部真实配方并检查叶子、深度和分支数；改布局可能让宽度或 SVG 单位爆炸，需覆盖深树、双配方、窄屏和容器 resize；Canvas 与 SVG 不共享渲染实现，发布前需分别做浏览器交互和微信真机验收。验证命令见 [TESTING.md](TESTING.md)。

## 8. 不做的范围

- 不做开放式 Agent Loop：确定性工具配确定性调度，模型不负责反复选工具（ADR-02）；
- 不让 LLM 写正式知识库或图谱，也不用 RAG 推测配方数值；
- 不做多租户、多主机分布式限流和跨主机共享额度（当前是单主机单副本定位）；
- 不把"图里没有路径"表述成"现实中不存在该关系"；
- 不在缺少困难评测证据时引入 reranker、补检索循环或更大模型；
- 不让 3D 档案载体承载或猜测知识事实；配方与问答内容始终由现有 DOM 和数据链呈现。

## 9. 决策记录（ADR）

| 编号 | 决策 | 理由与代价 |
|---|---|---|
| ADR-01 | 配方使用结构化数据 | `output/recipes.json` 是唯一数据源：原料、数量、设备和耗时必须精确；RAG 只负责解释性知识，不能猜配方；提取层保留完整真实配方，循环和分支限制由展示树处理 |
| ADR-02 | 知识问答采用确定性编排 | 先走配方、设备、枚举、实体和图关系等确定性路径，开放问题才使用受约束语义规划与答案生成；规划器只产生实体、主题、子查询和白名单路线，不提供事实答案；当前不引入开放式 Agent Loop |
| ADR-03 | RAG 与图谱互补 | 图谱保存明确、可追溯的关系；态度、性格、喜好和剧情概括回到原文；图未命中只表示当前图没有证据，必须回退文本检索；LLM 不允许直接写正式图谱 |
| ADR-04 | 原始数据不可变，索引可重建 | WIKI JSON 是只读事实源；知识库、RAG、mention、图谱和媒体索引均由脚本生成；错误通过修构建规则和重建解决，不手改派生数据库；构建产物必须包含来源和策略指纹 |
| ADR-05 | 流式与整包共用业务逻辑 | `/api/ask` 和 `/api/ask/stream` 共用路由、检索、拒答和上下文，只有传输不同；Web 优先 SSE，小程序与评测保留整包接口；流式改善感知延迟，不用于声称总耗时下降 |
| ADR-06 | 模型完成状态必须明确 | 只有受支持的 `finish_reason` 才算成功，连接 EOF 或孤立 `[DONE]` 不足以证明答案完整；长度截断最多续写一次；输出开始后不自动重试，以免重复或拼接错误内容 |
| ADR-07 | 质量指标必须绑定版本 | 数据集、索引、检索参数、Prompt 和相关实现源码共同形成评测 manifest；无元数据历史成绩可用于观察，不能作为严格发布基线；高 Recall 只表示固定检索集的相关来源进入 Top-K，不代表答案正确（本轮 71 条快照的 Recall@5 是 98.59%，其中一条困难样本未命中） |
| ADR-08 | 用户反馈先隔离审核 | 普通 Trace 只存查询指纹、阶段、排名、耗时与用量；用户主动反馈时才保存问题和已展示答案，并进入 `pending_review`；只有人工补齐事实、来源、正确路线或拒答标签后，样本才能回放；反馈不自动改索引或 Prompt |
| ADR-09 | 部署默认单 worker、运行期离线 | 每个 worker 都会加载 embedding 和索引，因此默认 `WEB_CONCURRENCY=1`；镜像构建时下载模型并重建索引，运行阶段离线；公网只开 80/443，容器端口只绑定宿主机回环，Nginx 负责 HTTPS 与入口限流，运维细节见 [DEPLOYMENT.md](DEPLOYMENT.md) |
| ADR-10 | 双端共享契约，不共享渲染 | Web 用 React SVG，小程序用 Canvas；两端共享 API 数据、名称规则、配方不变量和答案引用约定，各自实现 DOM、触控和像素比适配；后续优先抽纯数据布局与 `EvidenceRef`，不强行共享平台 UI 代码 |
| ADR-11 | 视觉服务于查询 | 界面采用官网黄黑工业语言，但搜索和结果优先；短交互动画使用 0.2–0.4 秒、区块单向揭示、环境层慢循环；所有功能在 `prefers-reduced-motion` 下完整可用；统计和准确率从真实元信息读取，不在 UI 写死 |
| ADR-12 | 中文小型 embedding 模型 + 嵌入式向量库 | `BAAI/bge-small-zh-v1.5`（`rag_config.py` 单一来源，可用 `EMBEDDING_MODEL` 覆盖）存放在 ChromaDB `PersistentClient`，集合固定 `hnsw:space=cosine`；语料是中文游戏百科、部署目标是 CPU 单机离线镜像，故选体积小、中文检索效果好、不产生按量费用的组合，代价是精度上限低于大模型；换模型必须全量重建并隔离输出目录（不同模型的向量不能共存，`build_rag.py` 已强制该行为），升级前须先由固定评测证明收益 |
| ADR-13 | 多路召回 + RRF 融合，而不是单一向量检索 | 召回由名称、BM25、向量、mention 和实体直取共同完成，`rag_config.py` 固定 `BM25_TOP_N=20`、`VECTOR_TOP_N=20`、`RRF_K=60`、`FINAL_TOP_K=5`；游戏专有名词与短名称（"负山""诀"）容易被纯向量漏掉，必须保留字面命中；不同检索器的分数不可比，排名倒数融合比手工加权更稳定，且参数集中在一处便于消融实验 |
| ADR-14 | 切分与上下文预算显式化 | 条目优先整条入库，超长按 `sections` 拆，`sections` 缺失或未覆盖时回退并补入 `full_text`（防静默漏索引）；chunk 文本带"分类 + 条目名"前缀，使专名同时进入 BM25 与向量；生成上下文使用 `focus_long_context()`（每来源 1800 字、最多 7 个窗口）按查询选择位置，而不是截取开头；回答预算 `GEN_ANSWER_MAX_TOKENS=1600`，截断时最多续写一次；所有预算变化都必须有回归测试，因为它们直接决定证据能否被看到 |
| ADR-15 | 图谱用 SQLite 属性表，而不是图数据库 | 2,405 个实体、10,076 条关系、单机部署，SQLite 足以支撑 1–3 跳路径查询，并带来单文件审计、可整库重建、运行期只读打开和零外部服务；代价是缺少图查询语言与跨主机并发；若将来多实例部署可替换为图数据库，但必须保留来源、证据、规则版本和确定性审计语义 |
| ADR-16 | 不引入编排框架 | 路由、检索、拒答、图查询和评测都是确定性代码，直接可读可测；LangChain / LlamaIndex / GraphRAG 框架会隐藏控制流、引入较大依赖与版本漂移，与本项目"每条结论可追溯到证据"的目标冲突；只有出现框架能明显降低维护成本的新需求时才重新评估 |
| ADR-17 | 流式准入属于响应生命周期 | 流式路由只负责构造响应；并发名额、次数额度和 Trace 在 ASGI 真正执行响应后取得；响应层在生成线程启动时移交名额，此后由线程在所有出口统一释放；未被执行的响应不会消耗名额或额度，同时保留并发已满时的 HTTP 429 |
| ADR-18 | 3D 是可降级的展示层，不是事实层 | Web 使用一个按需加载的 Three.js canvas 贯穿首页、过渡区与查询区，React DOM 继续负责搜索、结果、来源、按钮和无障碍语义；档案盒只作为中性展示载体，不绑定知识条目，也不参与配方或问答事实生成；相机、指针、滚动和抽取由一套协调状态驱动，避免多时间轴互相抢占；选该边界是为了获得空间深度、玻璃质感和可理解的模式转场，同时保证 WebGL 不可用、上下文丢失、静态模式和 `prefers-reduced-motion` 下业务仍完整；持续浏览可有轻微环境运动，档案稳定展开后停止渲染，不能把这种策略表述为固定帧率或固定功耗降幅 |
| ADR-19 | 生成门槛集中配置并由评测校准 | 普通向量召回的相关度阈值 `GENERATION_MIN_VECTOR_SIM` 定义在 `rag_config.py` 单一来源，并随检索参数写入评测 manifest，而不是散落在调用点的字面量；阈值过高会拒掉本来可回答的问题，过低会把无关召回交给模型编造答案，两种错误只能靠固定答案集对照发现；2026-09-14 依据在线答案评测把它从 0.30 校准为 0.45；实体直取，以及命中片段中含关键词、mention、直取或关系证据等人工确认上下文时不受该阈值影响，避免确定性证据被向量分数误拒；代价是阈值成为需要随语料与模型重新校准的参数，因此任何调整都必须带固定答案集的前后对照，不能只凭单例观感 |

数据细节见 [DEVELOPMENT.md](DEVELOPMENT.md)，接口见 [API.md](API.md)，检索与图谱实现见 [RETRIEVAL.md](RETRIEVAL.md)，验证方式见 [TESTING.md](TESTING.md)，部署见 [DEPLOYMENT.md](DEPLOYMENT.md)；产品说明见 [../README.md](../README.md)。
