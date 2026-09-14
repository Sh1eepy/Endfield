# 开发指南

本文覆盖环境、项目结构、工具清单、改动路径与双端客户端实现。文档总入口见 [README.md](README.md)，
产品门面见根 [README.md](../README.md)，整体边界与技术选型见 [ARCHITECTURE.md](ARCHITECTURE.md)，使用者视角见 [USER_GUIDE.md](USER_GUIDE.md)。

## 1. 环境

- Windows / PowerShell；Python 3.12，推荐 conda 环境 `endfield`；Node.js 24；
- embedding 离线加载：`HF_HUB_OFFLINE=1` 且 `local_files_only=True`，运行时索引与 embedding 不联网；
- 后端在 `0.0.0.0` 监听时，本机浏览器访问使用 `http://127.0.0.1:8000`；
- 后台进程的 `sys.stdout` 可能为 `None`，设置编码前先判断；
- 终端中文可能乱码或受 GBK 影响，重要结果写入 UTF-8 文件后再读取。

## 2. 首次启动

```powershell
pip install -r requirements.txt
Set-Location web
npm ci
npm run build
Set-Location ..
python scripts/start_server.py
```

`start_server.py` 默认单 worker 并预热 embedding 与索引；内存紧张可设 `RAG_PREWARM=0`。直接运行 uvicorn 不预热，首个问答会承担初始化开销。

## 3. 项目结构与目录职责

```text
docs/          开发者与使用者文档（总入口 README.md）
scripts/       数据构建、检索、图谱、API 与评测工具
web/           Vite + React 18 + TypeScript + framer-motion + Three.js，构建产物 web/dist 由 FastAPI 托管
miniprogram/   微信小程序，同一后端的移动入口
endfield_kb/   规范化知识库产物（22 个分类）
output/        配方、索引、图谱与评测产物
tests/         Python 离线回归测试
```

- 根 `README.md` 只回答"是什么、能做什么、怎么跑起来、数据从哪来"；改用户可见行为前先读 [USER_GUIDE.md](USER_GUIDE.md)，它是使用者视角的承诺面；
- 小程序复用同一个 FastAPI、配方数据、RAG 与知识图谱，不在客户端保存模型或 API Key；
- 原始 WIKI 快照与根目录既有历史数据文件只作事实源，日常开发不改写、不删除。

## 4. 改动路径

| 改动 | 先读 | 主要代码 | 必测 |
|---|---|---|---|
| 数据提取 | [ARCHITECTURE.md](ARCHITECTURE.md) | `build_kb_all.py`、提取脚本 | 构建审计、样本结构 |
| 配方树 | [ARCHITECTURE.md](ARCHITECTURE.md) | `recipe_index.py`、`api_server.py`、两端树组件 | 全量树不变量、双端交互 |
| RAG | [RETRIEVAL.md](RETRIEVAL.md) | `build_rag.py`、`rag_search.py`、`rag_ask.py` | 索引审计、检索/路由评测 |
| 图谱 | [RETRIEVAL.md](RETRIEVAL.md) | `build_knowledge_graph.py`、`graph_search.py` | 图审计、关系问法 |
| API | [API.md](API.md) | `api_server.py`、`api_security.py` | 参数、安全、流式、契约 |
| Web | 本文 §8 | `web/src/` | Vitest、build、响应式 |
| 小程序 | 本文 §9 | `miniprogram/` | Node test、开发者工具、真机 |
| 部署 | [DEPLOYMENT.md](DEPLOYMENT.md) | Docker、Compose、Nginx | 配置测试、容器与域名验收 |

测试矩阵、指标边界与发布门禁见 [TESTING.md](TESTING.md)。

## 5. 工具与命令

命令均从项目根目录执行。先复用现有工具，避免重复实现；新增脚本后在对应类别补一行职责和最小用法。

### 5.1 数据构建

| 工具 | 职责 | 最小用法 |
|---|---|---|
| `wiki_collector.js` | 在已登录 WIKI 页面内采集块式数据 | 浏览器控制台运行，凭据不离开浏览器 |
| `diff_wiki_snapshots.py` | 校验两份快照完整性，按稳定 ID 输出增删改、改名与分类差异；校验失败非零退出 | `python scripts/diff_wiki_snapshots.py OLD.json NEW.json --out output/update_YYYYMMDD/wiki_delta.json` |
| `build_kb_all.py` | 全量 JSON → 22 分类 JSONL/Markdown | `python scripts/build_kb_all.py` |
| `build_kb.py` | 旧版单分类构建，兼容保留 | `python scripts/build_kb.py --help` |
| `recipe_extract.py` | 提取完整配方库 | `python scripts/recipe_extract.py` |
| `recipe_index.py` | 配方加载、物品索引与名称解析库 | 由服务和评测导入 |
| `extract_media.py` | 提取封面、正文媒体、外链和引用 | `python scripts/extract_media.py` |
| `build_operator_details.py` | 生成干员结构化详情和语音 | `python scripts/build_operator_details.py` |
| `gen_jieba_dict.py` | 从条目名生成游戏专名词典 | `python scripts/gen_jieba_dict.py` |
| `remove_edge_background.py` | 指定素材的边缘连通底色透明化 | `python scripts/remove_edge_background.py --help` |

`inspect_wiki_entry.py` 检查单条 WIKI 数据；`search_chunks.py` 与 `extract_module.py` 只用于历史 SPA 逆向排查。

### 5.2 RAG 与图谱

```powershell
# RAG 首次全量 / 日常增量
python scripts/build_rag.py --inputs "endfield_kb/*.jsonl" --reset
python scripts/build_rag.py --inputs "endfield_kb/*.jsonl" --incremental

# 检索探针
python scripts/rag_search.py "天有洪炉需要什么材料" --top-k 5

# 图谱全量 / 增量 / 查询
python scripts/build_knowledge_graph.py
python scripts/build_knowledge_graph.py --incremental
python scripts/graph_search.py "陈千语和诀的关系"
```

| 模块 | 职责 |
|---|---|
| `rag_config.py` / `rag_prompts.py` | embedding 与检索参数的单一来源；生产 Prompt 与内容哈希版本 |
| `rag_search.py` / `intent_router.py` | 名称、BM25、向量与 RRF 融合；强规则意图识别与可选 LLM 兜底 |
| `rag_ask.py` | 枚举、结构化直查、语义规划、多路检索、生成与降级 |
| `llm_client.py` | OpenAI 兼容客户端、受限重试、续写、流式完成校验和操作预算；JSON 去参重试只处理明确的不支持错误 |
| `build_knowledge_graph.py` | 白名单关系提取、来源哈希与增量替换 |
| `graph_search.py` / `graph_aliases.json` | 实体、关系和最多三跳证据路径；人工审定别名 |

mention 反查由 `rag_ask.build_mention_index()` 懒构建并缓存到 `output/mention_index.json`；缓存保存知识源指纹，数据变化会自动重建，当前没有独立构建脚本。

### 5.3 服务与客户端

```powershell
# 推荐：单进程默认预热
python scripts/start_server.py

# 仅本地调试、无启动预热
python -m uvicorn scripts.api_server:app --host 0.0.0.0 --port 8000

# Web：安装、测试、构建、开发（5173，自动代理 /api）
Set-Location web
npm ci
npm test
npm run build
npm run dev
```

- `api_server.py`：FastAPI、静态托管、SSE、媒体代理和健康接口；
- `api_security.py`：令牌、SQLite 次数额度、代理客户端地址与管理接口保护；
- `start_server.py`：`.env` 预加载、worker、端口、代理信任和单进程预热；部署与反向代理见 [DEPLOYMENT.md](DEPLOYMENT.md)。

### 5.4 审计、评测与反馈

```powershell
python scripts/rag_audit.py --fail-on-error
python scripts/graph_audit.py --fail-on-error
python scripts/eval_retrieval.py --out output/eval/final_reviewed.json
python scripts/eval_pipeline.py
python scripts/eval_answers.py
python scripts/eval_graph.py
python scripts/audit_relation_queries.py
python scripts/build_eval_manifest.py
python scripts/quality_gate.py
python scripts/quality_gate.py --require-versioned-results
```

`eval_rag.py` 和 `test_rag_semantic.py` 是早期或专项探针；正式回归以 `eval_retrieval.py`、`eval_pipeline.py`、`eval_answers.py` 和版本化门禁为准。

```powershell
# 线上坏例闭环
python scripts/review_bad_cases.py list
python scripts/review_bad_cases.py approve <feedback_id> --route rag --facts "必要事实" --sources "可接受来源"
python scripts/replay_bad_cases.py --mode retrieval
python scripts/replay_bad_cases.py --mode pipeline --allow-llm
python scripts/replay_bad_cases.py --mode answer --allow-llm
```

- `rag_trace.py` 保存脱敏阶段数据和反馈隔离区；`rag_monitor.py` 汇总进程内请求与延迟指标；`eval_case.py` 统一固定评测和 Replay 的 Gold schema；
- `--allow-llm` 与 `eval_answers.py --judge` 会产生在线模型调用，普通离线测试不使用密钥。

### 5.5 文档维护

| 工具 | 职责 | 最小用法 |
|---|---|---|
| `check_docs.py` | 检查仓库 Markdown 中的本地相对链接，不访问网络 | `python scripts/check_docs.py` |
| `build_changelog_detail.py` | 从 git 历史生成详细更新日志骨架，并按短哈希保留人工说明 | `python scripts/build_changelog_detail.py` |

文档移动、改名或新增后运行 `check_docs.py`；提交后运行 `build_changelog_detail.py`，让 [CHANGELOG_DETAIL.md](CHANGELOG_DETAIL.md) 跟上最新提交（它只读 `git log`，不修改代码或数据）。

### 5.6 前端空间验收

`check_spatial_frontend.mjs` 使用现有 Playwright 与 Edge 对本地 5173 页面执行两种视口的截图、指针拾取、抽取/收回、几何坐标、等待反馈和上下文丢失检查；最小用法 `node scripts/check_spatial_frontend.mjs <playwright包目录> output/frontend-spatial/recheck`。不安装新依赖，查询响应仅在浏览器内模拟；截图与 JSON 是可重建验收产物，不进入普通 Git 历史。

### 5.7 官方素材

`fetch_official_design_assets.py` 从公开官网 CDN 下载选定图片到 `web/assets/official/`，记录 URL、大小和 SHA256；它只下载图片、不执行官网脚本，运行需要网络权限。当前清单包含五位首页角色、入场/首页横版宣传主视觉和 PlayStation 官方展示页的 Query 轨道背景；`python scripts/fetch_official_design_assets.py` 可补齐缺失图片并重建来源清单。使用与版权边界见 [ASSETS.md](ASSETS.md)。

## 6. 数据与配置纪律

- 原始 WIKI JSON 是只读事实源；解析不到时如实报告，不补猜测数据；
- `endfield_kb/` 和 `output/` 是可重建产物，修构建规则后重建，不手改数据库结果；
- `.env` 不提交；`LLM_API_KEY` 只在运行环境注入，前端和小程序不保存密钥；
- RAG/图谱运行文件可能被服务占用，重建前停服或使用独立目录；
- 接口响应变化同步更新 Web 类型、小程序封装、文档和契约测试。

## 7. 本地工作流与常见陷阱

本地工作流：

1. 用 `rg` 和本文件 §5 确认已有工具，避免重复实现；
2. 用最小真实样本复现问题，记录当前代码、数据、索引与 Prompt 版本；
3. 修改职责所属模块，保持确定性路径与模型路径分离；
4. 先跑针对性测试，再按 [TESTING.md](TESTING.md) 扩大验证；
5. 更新对应专项文档与 [CHANGELOG.md](CHANGELOG.md)，提交后跑详细日志脚本；
6. 性能结论分冷启动、warm、本地检索、在线 LLM 和缓存命中，避免混用。

常见开发陷阱：

- 把 `/api/ask/stream` 的显示提速写成总耗时下降：流式主要改善感知延迟；
- 把 `LLM_TOTAL_TIMEOUT` 写成整道问题 deadline：当前它只约束一次 LLM 客户端操作及其重试、续写；
- 用名称子串选择短实体：应优先完整名称并保留稳定 ID；
- 用单一 chunk 代表长来源：同来源多个证据应有界聚合；
- 把图无路径当作否定事实：必须回退文本并说明证据边界；
- 用 `npm install` 漂移锁文件：日常安装用 `npm ci`，依赖升级单独处理。

## 8. Web 客户端实现要点

技术栈 Vite + React 18 + TypeScript + framer-motion + Three.js；源码在 `web/src/`（`App.tsx` 编排 + `components/` + `styles/` + `api.ts` + `types.ts`）。主色 `#fffa00`，设计 token 集中在 `web/src/styles/tokens.css`；桌面固定左轨、移动端紧凑顶栏，装饰不得遮挡表格、媒体和按钮。日常反馈 0.2–0.4 秒，品牌开场与日常交互区分强度；`EntryCurtain` 约 6 秒、8 秒硬超时，每会话默认一次，可跳过/重播，减少动态效果时直接进入页面。官网素材在 `assets/official/`，`sources.json` 记录原始 URL、字节数与 SHA256，版权归原权利人，页面标明非官方社区工具。

| 区域 | 组件 | 说明 |
|---|---|---|
| 顶部 | `TopBar` | 品牌、后端连接状态、简短说明 |
| 搜索 | `SearchBox` | 配方树/知识问答双模式，各自独立保存 query |
| 结果 | `ResultPanel` + `AskResult`/`SynTree`/`KbCard`/`DeviceCards` | 纵向配方树、带来源的知识回答、结构化卡片 |
| 干员 | `OperatorDossier` | 章节导航、局部 Tab、图片/视频卡、音频、独立表格滚动条 |
| 首页 | `Hero` | 全屏角色拼贴、遮罩换人、文字错峰入场、操作区；图片本地加载 |
| 空间 | `ArchiveExperience` + `archiveScene` | Home/过渡/Query 共用 canvas；双螺旋、玻璃档案、中央环、抽取与降级 |
| 等待 | `RetrievalStatus` | 真实 SSE 阶段、不确定进度、等待秒数与停止入口 |
| 开场 | `EntryCurtain` | 会话首次进入的分段开场（约 6s，8s 硬超时） |

答案渲染：`AskResult`/`AnswerMarkdown` 把 `**加粗**`、`*斜体*`、`` `代码` ``、列表和表格转成 React 节点（全库无 `dangerouslySetInnerHTML`），`[来源N]` 渲染为可点击角标；小程序端有等价实现。

流式输出（网页知识问答默认走 `POST /api/ask/stream`）：事件序列 `phase`（受理/检索中）→ `meta`（意图 + 来源先亮）→ `delta`×N → `done`（含 trace_id/feedback_snapshot）。

- `api.ts` 的 `fetchAskStream` 用 fetch + ReadableStream 自行解析 SSE，无第三方依赖，支持 AbortSignal 中断；
- `App.tsx` 维护流式状态机：`meta` 一到就渲染来源，`delta` 按约 80ms 节流合并重渲染；
- 流式期间正文按安全纯文本增量显示，`done` 后一次性转为完整 Markdown、来源跳转和反馈视图；缺少 `done` 不能缓存成完整答案；
- 结果面板在 loading→首段正文时不重新挂载，避免入场动画遮住首 token；生成期间可主动停止并保留当前内容；
- 旧后端没有该接口时抛 `StreamUnavailableError`，自动回退整包 `/api/ask`；小程序仍走旧接口。

干员详情：数据来自 `scripts/build_operator_details.py` → `output/operator_details.json`，经 `/api/synthesis?item=干员名` 的知识库结果附带 `operator_detail`，由 `OperatorDossier` 渲染。

- 章节和同类多段内容用局部按钮切换；WIKI 颜色 token 映射为前端样式，主/副能力保持视觉区别；
- 表格外层是独立横向滚动容器 + 可拖动状态条；媒体用完整图库卡片，不塞进标题区；
- 音频当前页按钮播放、再点暂停，加载失败显示明确状态（不空白）；
- 远程 WIKI 媒体走受限代理（`/api/media`），失败有兜底提示。

维护重点（改前端前必读）：

- 改 DOM 结构/交互前先跑 `tests/test_frontend_contract.py` 与 `web/tests/`；
- 媒体代理：`/api/media` 只允许可信 WIKI 域名（`bbs.hycdn.cn`），禁止放开白名单；
- 空间层：Three.js 只改 `scene/` 与 `ArchiveExperience` 桥接，不把业务事实写入 `userData`；新增资源必须纳入 `dispose()`；
- 响应式：新视觉效果至少检查 1440×900、390×844、窄屏触摸、上下文丢失和减少动态效果；
- 素材路径：一律用 `/assets/...`，不要依赖开发机绝对路径（dev 由 vite 代理 `/assets`，build 拷贝进 dist）；
- 安全：渲染 LLM/网络数据一律走 React 文本节点；请求 URL 用 `encodeURIComponent`；错误响应解析后端的 `detail` 展示给用户；
- 性能：动态场景包约 566KB（gzip 约 142KB），仍有 Vite 大包提示；中文字体约 17.8MB，未做不安全子集化。

后续可做（远期设想，不是当前能力）：把问答与配方请求抽成 session hook 与小型状态机、来源详情统一消费 `EvidenceRef`、URL 保存模式与实体 ID、配方树布局抽成纯数据模块供导出复用。

## 9. 小程序实现要点

小程序是网页端的移动入口，复用同一个 FastAPI、配方数据、RAG 和知识图谱，不在小程序里保存模型或 API Key。已有能力：

- 配方制造与知识问答使用独立查询词，首次进入均为空；名称联想、本地搜索历史与后端连接状态；
- 可拖动、缩放、折叠的纵向 Canvas 合成树；知识问答、引用来源、检索片段与结构化配方结果；
- 干员档案、富文本表格、图片、语音和外部视频入口；引用表格保持完整 Markdown 块，普通引用角标可点，`干员语音` 来源会回到对应干员；
- KB 的 link、entry 与行内图片保留，WIKI 图片和音频统一走受限媒体代理；视觉与 Web 端统一为终末地黄黑工业档案风格，并针对小程序触控与主包体积适配；首页角色立绘与地景图复用 `web/assets/official/` 的已归档官网素材，小程序内只保留实际使用的三份副本。

开发者工具运行：先在项目根目录启动单进程后端，再在开发者工具「导入项目」指向本目录；模拟器默认请求 `http://127.0.0.1:8000`，公共配置在 `project.config.json`。

```powershell
$env:WEB_CONCURRENCY = "1"
python scripts/start_server.py
```

真机调试（手机里的 `127.0.0.1` 是手机本身，不能访问电脑后端）：

1. 查询电脑局域网 IP，例如 `192.168.1.20`；
2. 把 `app.js` 的 `apiBase` 临时改成 `http://192.168.1.20:8000`；
3. 确认后端监听 `0.0.0.0`，手机和电脑连接同一网络；
4. 开发者工具调试阶段关闭合法域名校验，并按需允许 Windows 防火墙端口；
5. 调试后不要把个人机器 IP 提交到仓库。

正式发布：小程序正式版只能连接已配置的 HTTPS 服务。发布前应部署后端并确认 `/api/health` 正常，把 `apiBase` 改成线上 HTTPS 域名，在微信公众平台配置 request 合法域名，真机检查名称联想、配方树、RAG 回答、引用、图片和语音，确认 `.env` 与任何 API Key 都只存在于后端。`project.private.config.json` 是个人开发者工具设置，已被 `.gitignore` 排除；`project.config.json` 是团队公共配置，继续提交。

技术边界与测试：

- 小程序仍使用 `wx.request` 整包问答，问答单独使用 180 秒超时，普通接口保持 30 秒；当前未接 SSE，Web 的流式行为不能直接当作小程序能力；
- 配方树使用 Canvas，需独立处理像素比、图片缓存、缩放、拖动、折叠和卸载时的定时器清理；
- Markdown 转换为受控 rich-text，必须覆盖表格、列表和其中的 `[来源N]`；
- Node 模拟测试只验证请求与渲染逻辑，不等于开发者工具或真机验收；发布前至少在 Android、iOS 检查长答案、图片/音频、后台切换、弱网、滚动和树手势。

后续可做（远期设想）：环境化 `apiBase` 与发布期拒绝 HTTP/本机地址、可取消的请求封装、与 Web 共用纯数据树布局和 `EvidenceRef` schema；只有验证目标基础库和代理链路支持稳定分块读取后，再评估流式问答。

## 10. 双端共同不变量与已知边界

交互不变量（设计资产，勿随意打破）：

- 空 query 只显示入口和示例，不默认查询某个物品；搜索建议前缀优先，再做包含匹配；
- 模式切换不自动发送请求；相同知识问题优先读本次会话缓存；新请求必须中止或隔离旧响应，旧结果不能覆盖新问题；
- 宽表与配方树各自使用内部滚动容器，不依赖整页底部滚动条；图片保持可辨认尺寸，视频/图库不塞进窄标题栏；
- 等待反馈：`phase`/`meta` 不得提前结束进度提示，不确定过程不显示伪百分比，结果展开后提示不得覆盖正文；
- 触摸设备保持浏览器原生纵向滚动，不得用 `touch-action` 接管纵向手势（历史缺陷：`pan-x` 会吃掉查询区上方的滑动）；手机 pointer 不驱动 3D，`touch-action` 保持 `pan-y`；
- 所有动画遵守 `prefers-reduced-motion`（同时覆盖 CSS 与 JS），开场有硬超时；
- 空间层只负责氛围、镜头和档案展示载体：不得绑定知识条目，不得产生配方或问答事实，不得遮挡来源、表格和操作按钮；未使用 RhineLabUI 的 Logo、档案数据、字体、声音或 GLB 模型，`transition.ts` 的临界阻尼计算参考其 MIT 许可源码；
- 业务状态仍由 `App.tsx` 管理：两个模式的草稿与缓存独立，配方只读 `output/recipes.json`。

降级与已知边界：

- Three.js 仅在空间进入视口、页面可见且允许动态效果时加载；切到静态场景会释放 renderer；WebGL 不可用、初始化失败或上下文丢失时保留官方地景/纹理和全部业务交互；稳定展开、离开视口或标签页进入后台后停帧；
- 不承诺固定 60fps、固定功耗降低百分比或真机风扇表现；
- 当前浏览器验收的问答使用本地延迟 SSE 模拟，不代表真实 LLM 首字延迟或答案质量；尚未量测实体手机、长期显存、GPU 功耗和稳定帧时间；
- 小程序只有 Node 模拟测试，开发者工具与真机尚未验收；弱网、后台切换和长答案表现需在真机复核；
- 代码与本文件是后续维护的当前事实来源，历史验收报告只描述当时状态。
