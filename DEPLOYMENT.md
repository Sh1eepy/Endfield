# DEPLOYMENT.md — Docker 与 Railway 部署

## 推荐架构

使用一个 Railway Docker 服务同时托管 FastAPI、D3 前端和完整 RAG。前端使用相对路径访问 `/api/*`，因此不需要拆分 Vercel 服务，也没有额外跨域配置。

## 为什么镜像构建时重建 RAG

`output/rag/chroma/` 和本机 Hugging Face 模型缓存不进入 Git：前者可重建，后者体积大。Dockerfile 在构建阶段：

1. 安装锁定版本的 Python 依赖；
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
3. 在 Railway Variables 中设置 LLM 环境变量。不要上传 `.env`，不要把 Key 写入 Dockerfile。
4. 等待构建完成；健康检查路径为 `/api/health`，超时为 300 秒。
5. 生成公开域名后访问根路径，抽检配方树与知识问答。

Railway 会注入 `PORT`，容器启动命令自动使用它。若模型下载阶段失败，优先检查构建网络和磁盘/内存额度，不要关闭运行阶段的离线设置来绕过问题。

## 发布前验收

```powershell
python -m unittest discover -s tests -v
python -m compileall -q scripts tests
python scripts/eval_retrieval.py --out output/eval/final_reviewed.json
```

当前本机未安装 Docker，因此仓库内已完成配置和静态校验，但实际 `docker build` 必须在安装 Docker Desktop 后或 Railway 构建环境中完成。
