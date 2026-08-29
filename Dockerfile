# ============ 阶段 1：前端构建（Node） ============
FROM node:22-slim AS web-build
WORKDIR /app/web

# 先复制依赖清单安装（利用缓存层）
COPY web/package.json web/package-lock.json ./
# --ignore-scripts：esbuild 新版二进制走 optionalDependencies，无需 postinstall 下载
RUN npm ci --ignore-scripts

# 再复制源码构建
COPY web/ ./
RUN npm run build

# ============ 阶段 2：Python 运行时 ============
FROM python:3.12-slim

ARG APP_VERSION=unknown

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf-cache \
    APP_VERSION=${APP_VERSION}

WORKDIR /app

COPY requirements.txt ./

# 服务端只做 CPU embedding。先从 PyTorch 官方 CPU 仓库锁定 torch，避免
# sentence-transformers 在 Linux 上解析出数 GB 的 CUDA/cuDNN 依赖。
RUN python -m pip install --no-cache-dir --retries 8 --timeout 120 \
      --index-url https://download.pytorch.org/whl/cpu "torch==2.13.0+cpu" \
    && python -m pip install --no-cache-dir --retries 8 --timeout 120 \
      -r requirements.txt

# 先复制单一配置源并缓存 embedding 模型；随后切离线模式重建可复现的 Chroma 索引。
COPY scripts/rag_config.py ./scripts/rag_config.py
RUN python -c "from sentence_transformers import SentenceTransformer; from scripts.rag_config import EMBEDDING_MODEL; SentenceTransformer(EMBEDDING_MODEL)"

COPY scripts ./scripts
COPY endfield_kb ./endfield_kb
COPY output ./output
COPY web ./web
# 前端构建产物（阶段 1 产出）
COPY --from=web-build /app/web/dist ./web/dist

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

RUN python scripts/build_rag.py --inputs "endfield_kb/*.jsonl" --reset
RUN python scripts/build_knowledge_graph.py

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT', '8000') + '/api/health', timeout=3)"

CMD ["sh", "-c", "python scripts/start_server.py"]
