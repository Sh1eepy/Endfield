# scripts - 通用工具集

RAG、图谱、结构化查询的完整流程、协作规则、LLM 调用次数、截断预算和 Agent Loop 决策见
[`../KNOWLEDGE_SYSTEM_ARCHITECTURE.md`](../KNOWLEDGE_SYSTEM_ARCHITECTURE.md)。本文件维护工具与命令。

RAG 专项细节见 [`../output/RAG_TECHNICAL_OVERVIEW.md`](../output/RAG_TECHNICAL_OVERVIEW.md)。

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
| 端点 | 说明 |
|---|---|
| `GET /api/health` | 健康检查 |
| `GET /api/synthesis?item=重息壤` | 合成树（物品树 / 设备配方卡 / 歧义→候选列表 / 无配方→知识库信息 + 封面图/相关引用） |
| `GET /api/names` | 全部名称（前端模糊搜索联想） |
| `POST /api/ask` | RAG 问答（意图识别→路由→检索→LLM 带引用回答），body: `{"query":"重息壤是什么","top_k":5,"gen_answer":true}` |
| `GET /api/media?url=...` | WIKI CDN 图片/音频白名单同源代理（类型与 25MB 上限校验） |

自动托管前端：优先 `web/dist`（Vite+React 构建产物），无 dist 时回退 `web/`。
`/api/ask` 的 `query` 限制为 1～300 字符、`top_k` 限制为 1～10；并发满时返回 429。
当前界面采用多轮廓卡片语言（圆角胶囊、斜切多边形、不对称圆角），背景由圆环、波浪带、
多边形叠层构成；包含开机式入场动画、滚动视差与分区淡入，并兼容
`prefers-reduced-motion` 减少动态效果设置。
主工作区使用平行斜切边界与 3D 景深，背景不使用网格；克莱因蓝用于表格边缘和立体投影，
与工业黄形成局部撞色。字体层级按标题、说明与元数据分别强化，搜索输入尺寸保持稳定。
前端本地内置 Noto Sans SC（中文）与 Oxanium（英文/数字），许可证随字体保存；配方与问答
分别保留独立输入。透明小人作为框边贴纸和低透明分散背景，终末地图标用于开场、顶栏与首屏。

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
ask("终末地至今为止的主线任务有哪些")    # 枚举 → 知识库分类过滤 → LLM 分组整理
ask("解锁武陵地区需要什么条件")          # 多路检索 → LLM 整合开放问题
ask("重息壤是什么", gen_answer_=True)   # 知识 → RAG 检索 + LLM 带引用回答
```
主要路由：
1. **枚举查询**（"有哪些/列举/所有"）→ 知识库分类内过滤枚举（主线任务=任务分类含"第一章/进程"；
   干员/武器/活动=直接枚举该分类），LLM 分组整理回答
2. **结构化直查**：配方/设备意图或纯名称 → 配方库直查（含歧义候选/设备产物反查）
3. **语义检索规划**（开放问题）：一次受约束 LLM 调用输出问题类型、主题、实体、关键词、子查询和
   白名单 routes；规划器不能回答问题，也不能把猜测答案作为检索事实。随后走 RAG/全文关键词/mention。
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

## 注意
- 输出一律写 UTF-8 文件，不要只 print 到终端（Windows GBK 乱码）
- 模型加载必须离线（HF_HUB_OFFLINE + local_files_only）
- 浏览器访问用 `http://127.0.0.1:8000`（不要用 localhost，IPv6 坑）

## 离线回归测试

测试使用 Python 标准库 `unittest`，不需要安装 pytest，也不会调用真实 LLM：

```bash
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
```

覆盖健康检查、物品树、设备卡、歧义候选、知识库回退、空输入、循环/自循环剪枝、
名称缓存、问答入口参数传递，以及全部真实配方树的叶子与深度不变量。

## 部署

根目录提供 `Dockerfile`、`compose.yaml`、`requirements.txt` 和 `railway.json`；`deploy/` 提供自有服务器的 Nginx、HTTPS、更新与回滚手册。完整构建会下载 embedding 模型并在镜像内重建 RAG，运行阶段保持离线。密钥只能通过运行环境注入，详见 [`../DEPLOYMENT.md`](../DEPLOYMENT.md)。
