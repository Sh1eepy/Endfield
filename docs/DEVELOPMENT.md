# 开发指南

## 环境

- Windows / PowerShell；Python 3.12，推荐 conda 环境 `endfield`；Node.js 24；
- embedding 模型离线加载：`HF_HUB_OFFLINE=1` 且 `local_files_only=True`；
- 本机浏览器访问后端使用 `http://127.0.0.1:8000`；
- 后台进程的 `sys.stdout` 可能为 `None`，设置编码前先判断；
- 终端中文可能乱码，重要结果写入 UTF-8 文件。

## 首次启动

```powershell
pip install -r requirements.txt
Set-Location web
npm ci
npm run build
Set-Location ..
python scripts/start_server.py
```

`start_server.py` 默认单 worker 并预热 embedding 与索引；内存紧张可设 `RAG_PREWARM=0`。直接运行 uvicorn 不预热，首个问答会承担初始化。

## 改动路径

| 改动 | 先读 | 主要代码 | 必测 |
|---|---|---|---|
| 数据提取 | [DATA_PIPELINE.md](DATA_PIPELINE.md) | `build_kb_all.py`、提取脚本 | 构建审计、样本结构 |
| 配方树 | [SYNTHESIS.md](SYNTHESIS.md) | `recipe_index.py`、`api_server.py`、两端树组件 | 全量树不变量、双端交互 |
| RAG | [RAG.md](RAG.md) | `build_rag.py`、`rag_search.py`、`rag_ask.py` | 索引审计、检索/路由评测 |
| 图谱 | [GRAPH.md](GRAPH.md) | `build_knowledge_graph.py`、`graph_search.py` | 图审计、关系问法 |
| API | [API.md](API.md) | `api_server.py`、`api_security.py` | 参数、安全、流式、契约 |
| Web | [WEB.md](WEB.md) | `web/src/` | Vitest、build、响应式 |
| 小程序 | [MINIPROGRAM.md](MINIPROGRAM.md) | `miniprogram/` | Node test、开发者工具、真机 |
| 部署 | [DEPLOYMENT.md](DEPLOYMENT.md) | Docker、Compose、Nginx | 配置测试、容器与域名验收 |

## 数据与配置纪律

- 原始 WIKI JSON 是只读事实源；解析不到时报告，不补猜测数据；
- `endfield_kb/` 和 `output/` 是可重建产物，修构建规则后重建，不手改数据库结果；
- `.env` 不提交。`LLM_API_KEY` 只在运行环境注入，前端和小程序不保存密钥；
- RAG/图谱运行文件可能被服务占用，重建前停服或使用独立目录；
- 接口响应变化同步更新 Web 类型、小程序封装、文档和契约测试。

## 本地工作流

1. 用 `rg` 和 [TOOLS.md](TOOLS.md) 确认已有工具；
2. 用最小真实样本复现问题，记录当前代码、数据、索引与 Prompt 版本；
3. 修改职责所属模块，保持确定性路径与模型路径分离；
4. 先跑针对性测试，再按 [TESTING.md](TESTING.md) 扩大验证；
5. 更新对应专项文档、[PROJECT_STATE.md](PROJECT_STATE.md) 和 [CHANGELOG.md](CHANGELOG.md)；
6. 性能结论分冷启动、warm、本地检索、在线 LLM 和缓存命中，避免混用。

## 常见开发陷阱

- 把 `/api/ask/stream` 的显示提速写成总耗时下降：流式主要改善感知延迟；
- 把 `LLM_TOTAL_TIMEOUT` 写成整道问题 deadline：当前它只约束一次 LLM 客户端操作及其重试、续写；
- 用名称子串选择短实体：应优先完整名称并保留稳定 ID；
- 用单一 chunk 代表长来源：同来源多个证据应有界聚合；
- 把图无路径当作否定事实：必须回退文本并说明证据边界；
- 用 `npm install` 漂移锁文件：日常安装用 `npm ci`，依赖升级单独处理。
