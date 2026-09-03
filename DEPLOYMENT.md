# DEPLOYMENT.md — 部署总纲

> 更新日期：2026-09（增补流式问答的 Nginx 与启动预热说明）。本文是部署入口总纲：路径选择、关键设计决策与验收清单；
> 详细操作步骤见 [`deploy/README.md`](deploy/README.md)（自有服务器）、`deploy/API_SECURITY.md`（安全与限流）。

## 推荐架构

已有服务器和子域名时，推荐 `compose.yaml` 运行应用 + 宿主机 Nginx 提供 HTTPS/反向代理/限流：

```text
子域名 → Nginx/HTTPS → 127.0.0.1:8000 → Docker Compose → FastAPI + Web + RAG
```

网页使用相对路径访问 `/api/*`，因此任何部署都不需要拆分前端服务。没有自有服务器时才用 Railway。
朋友提供服务器时的权限分工见 `deploy/README.md` 第 0 节「协作模式」。

## 关键设计决策（为什么这么做）

- **镜像构建时重建 RAG**：`output/rag/chroma/` 和 HF 模型缓存不进入 Git（前者可重建、后者体积大）。
  Dockerfile 构建阶段装 CPU 版 torch（避免 CUDA 库入镜像）→ 下载 `bge-small-zh-v1.5` → `HF_HUB_OFFLINE=1`
  → 从 `endfield_kb/*.jsonl` 全量重建 Chroma/BM25/manifest → 运行阶段完全离线。
  首次构建慢且镜像大，这是完整离线 RAG 的成本；不要把真实密钥烘焙进镜像。
- **容器只监听 127.0.0.1:8000**：公网入口统一交给 Nginx，绝不改成 `0.0.0.0:8000`。
- **流式问答与启动预热**：容器入口是 `start_server.py`，单进程默认预热 embedding 模型与索引（冷启动落在健康检查
  `start_period` 内；内存极紧可设 `RAG_PREWARM=0`）。Nginx 模板（`deploy/nginx/endfield.conf`）已为
  `/api/ask/stream` 关闭 `proxy_buffering` 并把读超时放宽到 300s；更新线上 Nginx 时需同步，否则网页问答会失去逐字效果。
- **应用层也有保护**：问答 `query` 1~300 字符、`top_k` 1~10；每 IP 每分钟 6 次 / 每日 60 次 /
  全站每日 200 次（UTC 日窗口，SQLite 计数走 Compose 命名卷跨重建保留）；可选 Bearer 令牌私有模式；
  反馈接口使用同一 SQLite 的独立限额，并校验 Trace、客户端、问题和回答快照；
  详见 `deploy/API_SECURITY.md`。
- **问答 Trace 数据**：`RAG_TRACE_DB` 配置，Compose 默认放持久卷。普通 Trace 不含问题/答案正文，
  用户主动反馈才保存当次文本——该库与回放报告应按用户内容处理（限制管理员访问、纳入保留期、不提交 Git）。
- **公网只开 80/443**，不能直接暴露容器 8000 端口。

## 三条部署路径

| 路径 | 何时用 | 入口 |
|---|---|---|
| 本地 Docker | 本机验证/离线开发 | 见下「本地 Docker」 |
| 自有服务器 + 子域名 | 正式生产（推荐） | [`deploy/README.md`](deploy/README.md) 完整步骤 |
| Railway | 无自有服务器 | 见下「Railway」 |

### 本地 Docker

需要 Docker Desktop。不传 `.env` 时配方树/设备卡/知识库回退仍可用；在线 LLM 回答才需要注入 `LLM_API_KEY` 等：

```powershell
docker build -t endfield-synthesis .
docker run --rm -p 127.0.0.1:8000:8000 --env-file .env -e ASK_BUDGET_DB=/var/lib/endfield-security/ask-budget.sqlite3 -v endfield-api-security:/var/lib/endfield-security endfield-synthesis
```

浏览器打开 `http://127.0.0.1:8000`；`curl http://127.0.0.1:8000/api/health` 验证。

### Railway

1. 推仓库到 GitHub，Railway 建项目选该仓库（`railway.json` 选 Dockerfile 构建）；
2. 设置 LLM 环境变量 + `ASK_MAX_CONCURRENCY=2`；首次 `WEB_CONCURRENCY=1`，确认内存余量后再提（每 worker 独立加载模型/索引）；不要上传 `.env`；
3. 挂持久卷，`ASK_BUDGET_DB` 指向卷内文件（避免重建清零；多主机副本不能共用独立计数库）；健康检查 `/api/health` 超时 300s；
4. 生成域名后抽检配方树与问答。Railway 注入 `PORT`，容器自动使用。

模型下载失败先查构建网络与磁盘/内存额度，不要关闭运行阶段离线设置绕过。

## 微信小程序连接后端

模拟器用默认 `http://127.0.0.1:8000`；真机改 `miniprogram/app.js` 的 `apiBase` 为电脑局域网 IP（后端绑 `0.0.0.0`、同网、防火墙放行）。
正式发布改为 HTTPS 域名 + 微信公众平台配置 request 合法域名，API Key 只放后端。详见 `miniprogram/README.md`。

## 发布前验收

```powershell
python -m unittest discover -s tests -v
python -m unittest scripts.test_api_security -v
python -m unittest scripts.test_rag_trace -v
node --test miniprogram/tests/ask.test.cjs
python -m compileall -q scripts tests
python scripts/eval_retrieval.py --out output/eval/final_reviewed.json
```

任何公网环境上线后，仍需用正式域名复核健康检查、配方树与知识问答（本机模拟不能当线上验收）。
