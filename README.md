# Endfield 配方树与知识问答

基于《明日方舟：终末地》WIKI 数据的非官方工具。用户可查询物品和设备的完整配方链，也可检索干员、任务、武器、地点与人物关系。Web 与微信小程序共用 FastAPI、结构化配方库、RAG 和知识图谱。

## 主要能力

- **配方合成树**：345 条真实配方，叶子收敛到基础资源，每个物品最多两个配方并处理循环与深度；
- **知识问答**：确定性路由（结构化直查 / 枚举 / 图关系）+ 多路文本检索 + 有证据的可选 LLM 生成，证据不足时明确拒答；
- **知识图谱**：2,129 个实体、9,358 条带来源与证据的关系，支持正反问法与最多三跳路径，图未命中回退文本检索；
- **流式输出**：Web 走 SSE（`phase → meta → delta → done`），来源先亮、答案逐段显示；旧整包接口保留给小程序与评测；
- **双端客户端**：React + TypeScript 的 Web（React SVG 配方树 + 按需 Three.js 空间）与原生微信小程序（Canvas 树），共享同一套 API 契约；
- **可重建的数据链**：规范化知识库、RAG 索引、mention、图谱与媒体索引全部由脚本生成；RAG 与图谱带来源指纹和增量更新。

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.12、FastAPI + Pydantic v2、httpx、uvicorn |
| 检索 | `bge-small-zh-v1.5`（离线 CPU）、ChromaDB（cosine）、rank-bm25 + RRF 融合、jieba 专名词典 |
| 图谱 | SQLite 属性表 + 白名单规则提取（不用图数据库，见 [决策记录](docs/DECISIONS.md)） |
| 前端 | React 18 + TypeScript + Vite 6 + Framer Motion + Three.js；小程序原生 WXML/WXSS/Canvas |
| 质量 | unittest、Vitest + jsdom、node:test、索引审计与版本化质量门禁 |
| 交付 | Docker 多阶段构建（构建期重建索引）、Compose + Nginx、Railway 备选 |

## 快速启动

项目使用 Python 3.12、Node.js 24。本地 embedding 只允许离线加载；浏览器直连后端请使用 `127.0.0.1`。

```powershell
pip install -r requirements.txt
Set-Location web
npm ci
npm run build
Set-Location ..
python scripts/start_server.py
```

打开 `http://127.0.0.1:8000`。未配置 LLM 时，配方、设备和知识库检索仍可使用；生成式回答会按后端规则降级。LLM 配置参考 `.env.example`，真实密钥不得提交。`start_server.py` 默认单 worker 并预热 embedding 与索引；内存紧张可设 `RAG_PREWARM=0`。

## 接口速览

| 接口 | 用途 |
|---|---|
| `GET /api/synthesis` | 配方树、设备配方卡、知识库与干员详情 |
| `POST /api/ask` | 整包知识问答（小程序、评测使用） |
| `POST /api/ask/stream` | 流式知识问答（SSE，Web 默认） |
| `GET /api/names` | 搜索联想名称表 |
| `POST /api/feedback` | 用户反馈隔离区（人工审核后才回放） |
| `GET /api/health`、`GET /api/health/deep`、`GET /api/metrics` | 存活、深度索引检查、进程指标 |
| `GET /api/media` | WIKI 图片/音频同源代理（白名单 + 大小上限） |

端点边界与流式协议见 [API.md](docs/API.md)，限流与令牌见 [API_SECURITY.md](docs/API_SECURITY.md)。

## 验证

```powershell
python -m unittest discover -s tests -v
python -m unittest scripts.test_query_routes scripts.test_api_security scripts.test_rag_trace scripts.test_ask_stream scripts.test_backend_remediation -v
python scripts/check_docs.py
Set-Location web; npm test; npm run build; Set-Location ..
node --test miniprogram/tests/ask.test.cjs
```

索引、图谱或问答逻辑改动后，再运行 `rag_audit.py --fail-on-error`、`eval_retrieval.py`、`eval_pipeline.py`、`graph_audit.py`、`quality_gate.py`。
固定评测成绩的解释与边界见 [TESTING.md](docs/TESTING.md)：Recall 100% 只代表固定检索集召回，不代表回答正确率。

## 文档

文档总入口为 [docs/README.md](docs/README.md)。建议先读：

- [当前状态](docs/PROJECT_STATE.md)：已完成、已验证与待处理事项；
- [整体架构](docs/ARCHITECTURE.md)：模块边界和请求、数据流；
- [开发指南](docs/DEVELOPMENT.md)：环境、改动规则和本地流程；
- [测试与质量](docs/TESTING.md)：分层验证、指标解释和发布门禁；
- [Web 空间体验](docs/FRONTEND_EXPERIENCE.md)：开场、共享 3D 场景、查询反馈、降级与交互不变量；
- [部署总纲](docs/DEPLOYMENT.md)：本地、服务器和 Railway 路径。

## 核心目录

```text
docs/          设计、开发、测试、部署和历史文档
scripts/       数据构建、检索、图谱、API 与评测工具
web/           Vite + React + TypeScript 前端
miniprogram/   微信小程序
endfield_kb/   规范化知识库产物
output/        配方、索引、图谱和评测产物
tests/         Python 离线回归测试
```

原始 WIKI 数据和根目录既有历史数据文件只作事实源，不在日常开发中改写或删除。早期“生产流水线空间规划”方向已经废弃，不应重建。

## 数据与素材

项目数据来自《明日方舟：终末地》WIKI。页面使用的相关名称、图像与内容权利归原权利方所有；来源和校验信息见 [素材说明](docs/ASSETS.md)。
