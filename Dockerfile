FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf-cache

WORKDIR /app

COPY requirements.txt ./

# 服务端只做 CPU embedding。先从 PyTorch 官方 CPU 仓库锁定 torch，避免
# sentence-transformers 在 Linux 上解析出数 GB 的 CUDA/cuDNN 依赖。
RUN python -m pip install --no-cache-dir --retries 8 --timeout 120 \
      --index-url https://download.pytorch.org/whl/cpu "torch==2.13.0+cpu" \
    && python -m pip install --no-cache-dir --retries 8 --timeout 120 \
      -r requirements.txt

# 先缓存 embedding 模型；随后切离线模式重建可复现的 Chroma 索引。
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')"

COPY scripts ./scripts
COPY endfield_kb ./endfield_kb
COPY output ./output
COPY web ./web

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

RUN python scripts/build_rag.py --inputs "endfield_kb/*.jsonl" --reset
RUN python scripts/build_knowledge_graph.py

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT', '8000') + '/api/health', timeout=3)"

CMD ["sh", "-c", "python scripts/start_server.py"]
