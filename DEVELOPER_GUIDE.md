# 开发说明

## 先看整体

项目把《明日方舟：终末地》WIKI 数据整理成两个前端功能：配方合成树和知识问答。

```text
WIKI JSON
  ├─ build_kb_all.py → endfield_kb/ → RAG + 知识图谱
  ├─ recipe_extract.py → output/recipes.json → 配方树
  └─ extract_media.py / build_operator_details.py → 图片、音频、干员详情
FastAPI → web/index.html
```

RAG 和图谱的详细协作见 `KNOWLEDGE_SYSTEM_ARCHITECTURE.md`，工具命令见 `scripts/README.md`。

## 数据层

### 规范化知识库

`build_kb_all.py` 读取块式文档，按 22 个分类输出 JSONL、Markdown 和 `_catalog.json`。JSONL 保留：

- `item_id / name / category`；
- `sections / full_text`，供检索；
- `sections_struct`，供前端还原表格、图片和条目卡片。

原始 WIKI JSON 是只读事实源。解析不到的内容应报告，不能补写猜测数据。

### 配方

`recipe_extract.py` 生成 `output/recipes.json`。345 条配方全部保留，包括设备制造、盛装、矿机和原木。
知识库不能替代配方结构，合成树只使用这份 JSON。

### 媒体和干员

- `extract_media.py` 生成封面、正文媒体、外链和引用；
- `build_operator_details.py` 生成干员章节、Tab、富文本、图片和音频；
- 远程 WIKI 媒体由 `/api/media` 通过域名白名单代理。

## 合成树规则

入口是 `/api/synthesis`，核心逻辑在 `api_server.py`。

1. 叶子必须是基础资源：清水、惰气、息壤气、无产出配方矿物和种子类；
2. 排除自循环，按输入简单程度排序，每个物品最多展示 2 个配方；
3. 当前路径出现同一物品或深度超过 10 时剪掉该分支；
4. 名称有歧义时返回候选，不自动猜；
5. 没有配方时回退知识库详情。

修改这些规则后必须运行 `tests/test_api_server.py`，并确认所有真实树叶子仍符合基础资源规则。

## RAG 和图谱

`build_rag.py` 生成 Chroma、分类 BM25 和 manifest。首次用 `--reset`，以后用 `--incremental`。模型必须
离线加载。`build_knowledge_graph.py` 用白名单规则构建带来源证据的关系；不要让 LLM 直接写正式图谱。

在线问答在 `rag_ask.py`：结构化直查优先，其次是图关系，最后是文本多路检索。长文档使用查询聚焦窗口，
不能改回固定截取正文开头。

## API

| 接口 | 用途 |
|---|---|
| `GET /api/synthesis` | 配方树、设备配方、知识库/干员详情 |
| `GET /api/names` | 搜索建议名称 |
| `POST /api/ask` | 问答路由、检索和可选答案生成 |
| `GET /api/health` | 进程存活 |
| `GET /api/health/deep` | 索引和图谱深度检查 |
| `GET /api/metrics` | 当前进程问答指标 |
| `GET /api/media` | 受限 WIKI 媒体代理 |

## 前端

前端位于 `web/`，使用 **Vite + React 18 + TypeScript + framer-motion**（2026-08 由单文件 `index.html` 重构）。

```text
web/
├─ index.html           # 挂载点（保留 title / 字体预载）
├─ vite.config.ts       # dev 代理 /api → 127.0.0.1:8000；publicDir=assets
├─ package.json
├─ src/
│  ├─ main.tsx          # 入口
│  ├─ App.tsx           # 状态中枢（模式/查询/结果/缓存/历史）
│  ├─ api.ts / types.ts # 后端 API 客户端 + 响应类型（与 scripts 返回结构一一对应）
│  ├─ utils.ts          # 媒体代理 / 历史记录
│  ├─ styles/           # 分层 CSS：tokens/layout/components/tree/ask/kb/operator/entry/responsive
│  └─ components/       # EntryCurtain/TopBar/Hero/SearchBox/SideRail/ResultPanel/
│                       # SynTree/DeviceCards/KbCard/AskResult/OperatorDossier/Tip/EmptyState
```

- 开发：`cd web && npm install && npm run dev` → `http://localhost:5173`（自动代理 `/api` 到 8000）；
- 构建：`cd web && npm run build` → `web/dist/`；FastAPI 自动托管 `dist`（存在时优先，否则回退 `web/`）；
- 后端 API 变化时同步更新 `src/types.ts`（字段按需存在，前端按存在性判断）；
- 配方树为纯 React 递归 SVG（不再依赖 d3，布局常量 `X_UNIT/Y_STEP` 与原 d3.tree nodeSize 等价）；
- 需要保留的交互：配方和问答模式各自的 query；相同问答的会话缓存（`askCacheRef`）；
  空 query 入口；纵向图片节点和树内横向滚动；干员宽表各自滚动条；`prefers-reduced-motion`；
  素材署名。
- 修改 DOM id 或交互契约后同步更新 `tests/test_frontend_contract.py`（静态扫描 `web/src` 源码）。

## 本地验证

```powershell
python -m unittest discover -s tests -v
python scripts/eval_graph.py
python scripts/audit_relation_queries.py
python scripts/quality_gate.py
python -m uvicorn scripts.api_server:app --host 0.0.0.0 --port 8000
```

前端改动：`cd web && npm run dev` 后浏览器访问 `http://localhost:5173`；改完跑
`npm run build` 并确认 `web/dist` 可被 FastAPI 托管。浏览器直连后端时用 `http://127.0.0.1:8000`。
JS 改动可提取后用 `npx tsc --noEmit` 检查类型。

## 常见问题

- Windows 后台进程的 `stdout` 可能是 `None`，调用 `reconfigure` 前先判断；
- 终端中文可能乱码，重要结果写 UTF-8 文件；
- uvicorn 运行时会锁住 Chroma 文件，全量重建前先停服务；
- `.env` 含密钥，不提交；
- 新模块先看困难评测是否真的需要，避免增加没有收益的黑箱层。
