# scripts - 通用工具集

RAG、图谱、结构化查询的完整流程、协作规则、LLM 调用次数、截断预算和 Agent Loop 决策见
[`../KNOWLEDGE_SYSTEM_ARCHITECTURE.md`](../KNOWLEDGE_SYSTEM_ARCHITECTURE.md)（架构 + 路线图 + 门禁一体，
含监控评测工具表与结果快照）。本文件只维护工具与命令。

《明日方舟：终末地》**配方合成树** 项目的工具集。
（早期「生产流水线空间规划」工具已全部移除，勿重建。）

## 使用前提
- Python 3.10+ / Node.js 18+
- 相对路径基于运行命令的当前目录（项目根）

## 数据层工具

### 1. `wiki_collector.js` — 浏览器采集（需登录）
在已登录的 WIKI 页面控制台运行，借站内已认证 API 抓全量 JSON。
凭证不离开浏览器。

### 2. `build_kb_all.py` — 全量按分类提取知识库
把 `endfield_wiki_full_*.json` 全部条目按子分类提取为 jsonl + md：
```bash
python scripts/build_kb_all.py            # → endfield_kb/{分类}.jsonl/.md/_catalog.json
```
jsonl 格式 `{item_id,name,category,sections,sections_struct,full_text}`，直接喂给 `build_rag.py`。
渲染规则：entry（物品引用）→ `名称×数量`（空格分隔防粘连）；link（外链）→ 链接文本；
image 块 → `[图片](url)`；表格逐单元格渲染（不再丢数据）。
`sections_struct` 为结构化块（text/table/image/entry），供前端渲染真表格/真图片/物品卡片。

### 3. `build_kb.py` — 单分类知识库构建（旧工具，兼容保留）
```bash
python scripts/build_kb.py --sub-type-id 5 --output-prefix endfield_devices
```

### 4. `recipe_extract.py` — 从 WIKI 全量 JSON 提取配方
```bash
python scripts/recipe_extract.py          # → output/recipes.json（345 个配方，不做激进清洗）
```
保留设备制造/容器"盛装"/矿机/原木等全配方，供合成树完整展示"怎么造"。
循环/自循环等由合成树剪枝规则处理。合成树数据源。

### 5. `recipe_index.py` — 配方索引通用工具
`load_recipes / build_item_index / find_item_ids_by_name`，供 api_server 与 eval_rag 复用。
```python
from recipe_index import load_recipes, build_item_index, find_item_ids_by_name
```

### 6. `extract_media.py` — 提取图片/链接/引用结构信息
```bash
python scripts/extract_media.py          # → output/item_media.json
```
背景：build_kb_all / recipe_extract 渲染块式富文本时丢弃了图片 URL、外部链接、entry 数量与链接样式。
本脚本从 WIKI 全量 JSON 原样提取（**无需重新爬取，数据一直在原始 JSON 里**）：
- `cover` 条目封面图（1957/1958 覆盖）+ `illustration` 配图
- `images` blockMap 正文图片 URL（2046 个，bbs.hycdn.cn）
- `links` inline link 外部链接 url+text（291 个）
- `refs` inline entry 物品引用 id/name/count/showType（14693 条；showType=`card-big` 卡片 / `link-imgText` 图文链接）
供前端展示物品图片、引用卡片站内跳转。

### 6.1 `remove_edge_background.py` — 边缘连通白底转透明

用于角色贴纸等白底图片的确定性抠图，只移除与画布边缘连通的近白色区域，保留角色内部
封闭的白色脸部、眼睛和衣物。原图不覆盖，输出 RGBA PNG：

```bash
python scripts/remove_edge_background.py input.jpg web/assets/mascots/output.png
```

### 6.2 `build_operator_details.py` — 构建干员详情结构库

```bash
python scripts/build_operator_details.py   # → output/operator_details.json
```

从原始 WIKI 组件完整提取干员基本信息、章节/页签、富文本颜色与粗体、表格、图片、技能动态图、
潜能与明信片、档案、官方演示以及多语种语音。详情结构仍由前端直接渲染，避免 Top-K 或文本切片破坏
表格和媒体关系；其中“语音记录”章节的中文台词会由 `build_rag.py` 另行规范化进入 RAG。
`inspect_wiki_entry.py 名称` 可审计单条原始组件结构。

## RAG 层工具

### 轻量 GraphRAG：关系与多跳问答

```bash
python scripts/build_knowledge_graph.py                 # 全量构建 SQLite 图谱
python scripts/build_knowledge_graph.py --incremental   # 按来源 content_hash 增量替换边
python scripts/graph_search.py "陈千语和诀的关系"        # 1-3 跳证据路径
python scripts/graph_audit.py --fail-on-error           # 来源/hash/外键/证据/关系约束审计
python scripts/audit_relation_queries.py --fail-on-error # 自动正问/反问/是非问对称审查
python scripts/eval_graph.py                            # 单跳/多跳专项评测
```

图谱位于 `output/knowledge_graph/graph.db`。正式图接收任务人物/地点/前后置、干员身份认证、
章节语义引用、配方原料/产物、明确职务句式和人工审定别名；语义推断关系不直接入图。明确关系问题由 `rag_ask.py` 路由到图检索，
图谱缺少证据时回退原混合 RAG。完整 schema、增量、审查与门禁见
[`../output/GRAPHRAG_ARCHITECTURE.md`](../output/GRAPHRAG_ARCHITECTURE.md)。

“喜欢/中意/信任/性格”等解释性问题走 `hybrid_relation`：图谱只提供身份与事件定位，系统从任务、
档案、对话中提取局部原文窗口，生成时强制区分明确事实、合理解读和资料不足，解读结果不回写事实图。

### 7. `build_rag.py` — RAG 索引构建 / 增量更新
```bash
# 首次全量（清空重建，约 3 分钟）
python scripts/build_rag.py --inputs "endfield_kb/*.jsonl" --reset
# 之后增量：只重 embedding 变更条目 + 只重建变更分类 BM25 分片（秒级）
python scripts/build_rag.py --inputs "endfield_kb/*.jsonl" --incremental
```
产物（output/rag/）：`chroma/`（向量库）、`bm25/{分类}.pkl`（按分类分片）、
`chunks.json`（manifest，含条目级 content_hash 供增量对比）、`report.txt`。
默认同时读取 `output/operator_details.json`，将“语音记录”中的中文台词作为 `干员语音` 独立记录；
可用 `--no-operator-audio` 关闭。增量原理：内容、sections 与索引策略版本 hash 对比 → ChromaDB
分批 upsert/delete → 仅重建变更分类 BM25 分片。
增量运行还会核对 manifest 与每个 BM25 分片的 chunk 键；分片缺失、陈旧或损坏时自动自愈。
长条目若没有 `sections`，会回退切分 `full_text`；已有 sections 时也会补入未覆盖的描述/其他内容，
避免档案后半段、玩家攻略或语音线索静默漏索引。全量写 Chroma 按 1000 条分批，避免批量上限失败。

### 8. `rag_search.py` — 混合检索（向量 + BM25 分片 → RRF 融合）
```bash
python scripts/rag_search.py "天有洪炉需要什么材料" --top-k 5
```
模块：`from rag_search import RAGRetriever; r = RAGRetriever(); r.search(query, top_k=5)`
命中含 meta（分类/名称/ID）、text、score、vector_sim、bm25_score。

### 9. `eval_rag.py` — RAG 检索效果评测（对比结构化配方库）
```bash
python scripts/eval_rag.py                # → output/rag_eval_result.json
```
实测（2026-08）：Recall@5 = 66.7%（4/6）、MRR = 0.5；结构化配方库对照 100%。

### 10. `test_rag_semantic.py` — 口语化描述 → RAG 定位测试
验证"中等容量的电池"→中容谷地电池这类语义定位能力。

## 逆向工具（WIKI SPA 逆向用）

### 11. `search_chunks.py` — 在 webpack chunk 中搜索关键词
```bash
python scripts/search_chunks.py --chunk-dir chunks --patterns "item/catalog" --out logs/hits.txt
```

### 12. `extract_module.py` — 提取 webpack 模块完整代码
```bash
python scripts/extract_module.py --chunk-dir chunks --module-id 71188 --out-dir logs
```

## 服务

### 13. `api_server.py` — FastAPI 服务（配方合成树 + RAG 问答）
```bash
# 生产（默认 1 worker；每个 worker 都会加载一份模型与索引）
python scripts/start_server.py
# 本机开发调试（单进程，不重复加载模型）
WEB_CONCURRENCY=1 python scripts/start_server.py
```
多 worker 由 `start_server.py` 统一管理：worker 数取环境变量 `WEB_CONCURRENCY`（默认 1）。
首次上线保持 1，确认内存余量后再提高；`ASK_MAX_CONCURRENCY`（默认 2）限制每个 worker 同时执行的付费问答数。
`start_server.py` 启动默认预热 embedding 模型与 RAG/配方索引（冷启动移进健康检查 start_period；`RAG_PREWARM=0` 关闭）。
| 端点 | 说明 |
|---|---|
| `GET /api/health` | 健康检查 |
| `GET /api/synthesis?item=重息壤` | 合成树（物品树 / 设备配方卡 / 歧义→候选列表 / 无配方→知识库信息 + 封面图/相关引用） |
| `GET /api/names` | 全部名称（前端模糊搜索联想） |
| `POST /api/ask` | RAG 问答（意图识别→路由→检索→LLM 带引用回答），body: `{"query":"重息壤是什么","top_k":5,"gen_answer":true}` |
| `POST /api/ask/stream` | 同上路由的流式版（SSE：phase→meta→delta→done，body 一致；网页端默认使用） |
| `GET /api/media?url=...` | WIKI CDN 图片/音频白名单同源代理（类型与 25MB 上限校验） |

自动托管前端：优先 `web/dist`（Vite+React 构建产物），无 dist 时回退 `web/`。
`/api/ask` 的 `query` 限制为 1～300 字符、`top_k` 限制为 1～10；并发满时返回 429。
前端视觉设计与交互规则见 [`../web/README.md`](../web/README.md)。

## RAG 问答工具

### 14. `llm_client.py` — 在线 LLM 统一客户端（OpenAI 兼容协议）
```python
from llm_client import llm
llm.chat("重息壤是什么")            # 普通问答 → str
llm.chat_json("判断意图", ...)      # 强制 JSON → dict（意图识别/测试集生成）
llm.available()                    # 是否配置了 key
```
配置走环境变量 / `.env`（`LLM_API_KEY` / `LLM_BASE_URL` / `LLM_MODEL`），**代码零明文 key**；
未配置 key 时优雅降级不崩。密钥安全见 `.gitignore` + `.env.example`。

### 15. `intent_router.py` — 意图识别分层（L1 规则 → 可选 L3 LLM 兜底）
```python
from intent_router import classify_query
classify_query("重息壤怎么合成")   # → ('配方', 1.0, 'rule')
```
意图类别：配方 / 设备 / 知识 / 比较 / 数值。

### 16. `rag_ask.py` — RAG 问答路由（强规则 → 语义检索规划 → 多路检索 → LLM 生成）
```python
from rag_ask import ask
ask("重息壤怎么合成")                  # 配方 → 结构化直查
ask("诀从一级升到满级要多少材料")        # 知识库实体直取 → LLM 聚合回答
ask("终末地至今为止的主线任务有哪些")    # 枚举 → 知识库分类过滤 → 确定性完整清单
ask("解锁武陵地区需要什么条件")          # 多路检索 → LLM 整合开放问题
ask("重息壤是什么", gen_answer_=True)   # 知识 → RAG 检索 + LLM 带引用回答
```
主要路由：
1. **枚举查询**（"有哪些/列举/所有"）→ 知识库分类内过滤并返回确定性完整清单
   （主线任务=任务分类含"第一章/进程"；干员/武器/活动=直接枚举该分类），不经过 LLM/token 截断
2. **结构化直查**：配方/设备意图或纯名称 → 配方库直查（含歧义候选/设备产物反查）
3. **语义检索规划**（开放问题）：一次受约束 LLM 调用输出问题类型、主题、实体、关键词、子查询和
   白名单 routes；规划器不能回答问题，也不能把猜测答案作为检索事实。随后仅执行计划选中的文本路线；
   态度等解释性关系要求证据同时出现具体主体与关系对象/线索，并对来源去重
   图/结构化路线未命中且没有指定文本路线时回退实体直取、RAG 和关键词检索。
   有明确实体时关键词按“每个实体 + 主题词”检索，不用单个泛词全库补召回；主题证据优先于单纯 mention。
4. **实体直取**：抽到实体（"诀"）→ 直接取该条目全文当上下文，绕开 chunk 切分丢失表格
5. **解释性关系**：只有“人物—人物/组织/亲属”等关系规划才走证据窗口；“喜欢吃什么”等对象偏好走普通 RAG
LLM 生成带 `[来源N]` 引用的回答，检索相关度低时诚实拒答。

辅助数据：`output/mention_index.json`（"谁提到了X"反查索引，build_mention_index 生成）；
`PLACE_WORDS` 地名表（武陵/首墩/应龙关…，全文检索定位用）。

### 17. `gen_eval_set.py` — RAG 评测集自动生成（意图×难度矩阵）
```bash
python scripts/gen_eval_set.py --per-class 6 --out output/eval/eval_set.jsonl
```
在线 LLM 按 5 类意图 × 3 难度自动生成查询，gold 用结构化配方库/知识库自动核对
（不是让 LLM 自问自答）。未配 key 时降级为规则模板。

### 18. `eval_retrieval.py` — RAG 检索评测（严格命中判定）
```bash
python scripts/eval_retrieval.py --out output/eval/baseline.json
```
按 意图×难度 分表输出 Recall@k / MRR / Precision@k；命中判定严格（相等或互为简称包含），
不搞子串放水。基线 Recall@5=72%；当前人工审计版 `final_reviewed.json` 为 Recall@5=100%、MRR=97.3%。

### 19. `gen_jieba_dict.py` — 生成游戏专有名词 jieba 词典
```bash
python scripts/gen_jieba_dict.py    # → scripts/dict_zh.txt（1789 词）
```
扫描配方库+知识库名称，凡是 jieba 会切碎的名称收进词典；`build_rag.py` / `rag_search.py`
启动时自动加载，防止"重息壤/向心之引"被切碎导致 BM25 失配。

### 20. RAG 审计、监控与端到端评测

```bash
# 核对知识库、manifest、Chroma、BM25 分片和 mention 索引
python scripts/rag_audit.py --fail-on-error

# 25 条独立意图/路由集；加 --allow-llm 才调用在线意图兜底
python scripts/eval_pipeline.py --allow-llm

# 6 条答案/拒答小型黄金集；--judge 会产生在线调用
python scripts/eval_answers.py --judge

# 汇总索引、召回、路由和答案指标，任一低于阈值即返回非零退出码
python scripts/quality_gate.py
```

新增 API：`GET /api/health/deep` 做索引全链路一致性检查（LLM 仅检查配置，不产生费用）；
`GET /api/metrics` 返回当前进程的请求数、错误率、路由分布、空检索率、LLM 降级率与
p50/p95/max 延迟。指标是进程内滚动数据，服务重启会清零；生产部署可再接 Prometheus。

GitHub Actions 的 `rag-quality.yml` 会执行无网络单元测试和落盘指标门禁。在线 LLM 评判结果
由维护者显式刷新后提交，CI 不读取密钥、也不产生模型费用。

### 21. Trace、用户反馈与坏例回放（本地闭环）

```bash
# 固化数据集、索引、检索参数与 Prompt 版本
python scripts/build_eval_manifest.py

# 查看隔离区；批准时必须明确正确 route，并提供 Gold 事实、来源或“应拒答”标签
python scripts/review_bad_cases.py list
python scripts/review_bad_cases.py approve <feedback_id> --route rag --facts "必要事实" --sources "可接受来源"

# 默认是生产检索探针：保留直取兜底，不伪造 route，也不调用 LLM
python scripts/replay_bad_cases.py --mode retrieval
# pipeline 会调用生产语义规划器；answer 还会生成答案，二者均需明确允许在线费用
python scripts/replay_bad_cases.py --mode pipeline --allow-llm
python scripts/replay_bad_cases.py --mode answer --allow-llm
```

`rag_config.py` 是模型和检索参数的单一来源；`rag_prompts.py` 是实际生产/评测 Prompt 的单一来源，
版本由内容哈希自动生成，不再维护手写 `v1`。`build_eval_manifest.py` 固化跨机器一致的离线配置，
并统一文本换行后计算哈希；本机 `.env` 的实际 LLM 模型和 Git 状态写进每次评测元数据/Trace，
不会再让 GitHub Actions 因本机模型不同而误报 `eval_manifest_stale`。

`rag_trace.py` 将阶段耗时、路由、检索排名、上下文引用、模型/token 用量和版本写入
`RAG_TRACE_DB` 指向的 SQLite。普通问答只保存查询 SHA-256 与长度，不保存查询/回答正文；
只有用户主动点“没用”或“有用”提交时，`POST /api/feedback` 才把当次问题、可选说明和后端校验的已展示答案
写入 `pending_review` 隔离区。反馈不会自动进入评测集或质量门禁，必须人工批准并补 Gold。
固定评测和 Replay 共用 `eval_case.py` 的 Gold schema/确定性评分；Replay 按 retrieval → pipeline → answer
瀑布式归因，上一层失败就停止。报告写入已忽略的 `output/eval/replay/`，避免含用户文本的产物误提交。

## 注意
- 输出一律写 UTF-8 文件，不要只 print 到终端（Windows GBK 乱码）
- 模型加载必须离线（HF_HUB_OFFLINE + local_files_only）
- 浏览器访问用 `http://127.0.0.1:8000`（不要用 localhost，IPv6 坑）

## 离线回归测试

测试使用 Python 标准库 `unittest`，不需要安装 pytest，也不会调用真实 LLM：

```bash
python -m unittest discover -s tests -v
python -m unittest scripts.test_query_routes -v
python -m unittest scripts.test_api_security -v
python -m unittest scripts.test_rag_trace -v
node --test miniprogram/tests/ask.test.cjs
python -m compileall -q scripts tests
```

覆盖健康检查、物品树、设备卡、歧义候选、知识库回退、空输入、循环/自循环剪枝、
名称缓存、问答入口参数传递，以及全部真实配方树的叶子与深度不变量。

前端交互回归（在 `web/` 执行 `npm ci` 后）：

```bash
npm test
npm run build
```

`web/tests/` 使用本地 DOM 和模拟 API，验证旧响应隔离、模式输入保留、来源详情跳转、
树节点点击，以及 Markdown 表格/列表内引用和 HTML 安全性，不调用真实 LLM。
Web 答案由 `AnswerMarkdown.tsx` 生成 React 节点，支持表格、列表、标题、代码及行内引用；
`AskResult.tsx` 负责引用定位和来源跳转，语音来源打开所属干员档案。

### 前端工具链安全维护（2026-08-29）

- Vite 从 5.4.21 升至 6.4.3，依赖范围为 `~6.4.3`；esbuild 随之升至 0.25.12。
- React 插件最低版本调整为 4.7.0，兼容 Vite 6；React 18 和 Vitest 3.2.6 保持不变。
- 选择仍接收安全补丁的 6.4 分支，升级参考 [Vite 支持策略](https://vite.dev/releases) 和
  [5 → 6 迁移指南](https://v6.vite.dev/guide/migration)，未使用 `npm audit fix --force`。
- 本次 `npm audit` 为 0 告警；54 项后端基础测试、7 项检索编排测试、16 项前端测试及生产构建通过。
  前端测试含 3 项回环地址开发服务器检查：首页转换、React TSX 转换、自定义图片资源服务。
- 正式环境继续使用 `npm run build` 后的 `dist`，由 FastAPI 托管；开发端口不要暴露到公网。
  后续安装依赖使用 `npm ci`，升级后重新执行 `npm audit`、`npm test` 和 `npm run build`。

## 部署与 API 安全

根目录提供 `Dockerfile`、`compose.yaml`、`requirements.txt`、`railway.json`；`deploy/` 提供 Nginx/HTTPS/更新/回滚手册。
完整构建会下载 embedding 模型并在镜像内重建 RAG，运行阶段离线；密钥只能通过运行环境注入。
部署路径与设计决策见 [`../DEPLOYMENT.md`](../DEPLOYMENT.md)，操作步骤见 [`../deploy/README.md`](../deploy/README.md)。

API 安全（`api_security.py`：可选 Bearer Token、管理接口访问控制、SQLite 事务式频率/每日次数限制、
媒体代理重定向禁用 + 25 MiB 上限 + 并发限制）的配置与边界见 [`../deploy/API_SECURITY.md`](../deploy/API_SECURITY.md)。
`test_api_security.py` 模拟上游和 LLM，覆盖重定向、流大小限制、名额释放、鉴权、伪造 IP 头、共享额度和故障关闭。
