# DEPLOYMENT.md — Docker 与 Railway 部署

## 推荐架构

使用一个 Railway Docker 服务同时托管 FastAPI、D3 前端和完整 RAG。前端使用相对路径访问 `/api/*`，因此不需要拆分 Vercel 服务，也没有额外跨域配置。

## 为什么镜像构建时重建 RAG

`output/rag/chroma/` 和本机 Hugging Face 模型缓存不进入 Git：前者可重建，后者体积大。Dockerfile 在构建阶段：

1. 安装锁定版本的 Python 依赖，并从 PyTorch 官方 CPU 仓库安装 CPU 版 torch，避免把无用 CUDA 运行库打进镜像；
2. 下载 `BAAI/bge-small-zh-v1.5` 到镜像缓存；
3. 切换 `HF_HUB_OFFLINE=1`；
4. 从 `endfield_kb/*.jsonl` 全量重建 Chroma、BM25 和 manifest；
5. 运行阶段保持离线，不再访问 Hugging Face。

首次构建会较慢且镜像较大，这是完整离线 RAG 的成本。后续如果构建时间成为问题，可把索引和模型制作成单独基础镜像，但不要把真实密钥烘焙进镜像。

## 本地 Docker

需要先安装并启动 Docker Desktop：

```powershell
docker build -t endfield-synthesis .
docker run --rm -p 8000:8000 --env-file .env endfield-synthesis
```

浏览器打开 `http://127.0.0.1:8000`，验证：

```powershell
curl http://127.0.0.1:8000/api/health
curl "http://127.0.0.1:8000/api/synthesis?item=重息壤"
```

不传 `.env` 时，配方树、设备卡和知识库回退仍可用；需要在线 LLM 生成回答时，通过运行环境注入 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`。

## Railway

1. 把仓库推送到 GitHub。
2. Railway 新建项目并选择该 GitHub 仓库；`railway.json` 会选择 Dockerfile 构建。
3. 在 Railway Variables 中设置 LLM 环境变量。首次部署建议设置 `WEB_CONCURRENCY=1`，
   确认内存余量后再逐步提高到 2-4；每个 worker 都会各自加载 embedding 模型与 RAG 索引。
   不要上传 `.env`，不要把 Key 写入 Dockerfile。
4. 等待构建完成；健康检查路径为 `/api/health`，超时为 300 秒。
5. 生成公开域名后访问根路径，抽检配方树与知识问答。

Railway 会注入 `PORT`，容器启动命令自动使用它。若模型下载阶段失败，优先检查构建网络和磁盘/内存额度，不要关闭运行阶段的离线设置来绕过问题。

## 微信小程序连接后端

开发者工具模拟器可以使用 `miniprogram/app.js` 中默认的 `http://127.0.0.1:8000`。真机调试时需要改成电脑局域网 IP，
并确保 FastAPI 监听 `0.0.0.0`、手机与电脑同网且 Windows 防火墙允许对应端口。

正式发布时使用 Railway 或其他服务生成的 HTTPS 域名：

1. 把 `miniprogram/app.js` 的 `apiBase` 改为该 HTTPS 域名，不要带末尾斜杠；
2. 在微信公众平台把域名加入 request 合法域名；
3. 用真机分别抽检 `/api/health`、名称联想、配方树、知识问答、图片和语音；
4. 不要上传 `.env`，API Key 只放在后端服务变量中，不能写进小程序代码。

微信开发者工具的 `project.private.config.json` 只记录个人本地设置，已加入 `.gitignore`；公共的
`project.config.json` 继续进入版本控制。

## 发布前验收

```powershell
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
python scripts/eval_retrieval.py --out output/eval/final_reviewed.json
```

2026-08-21 已完成本地 Docker 镜像构建、容器启动和基础接口验证。Railway 上线后仍需使用公开域名复核健康检查、配方树与知识问答。
