FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/opt/hf-cache

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 先缓存 embedding 模型；随后切离线模式重建可复现的 Chroma 索引。
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-small-zh-v1.5')"

COPY scripts ./scripts
COPY endfield_kb ./endfield_kb
COPY output ./output
COPY web ./web

ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1

RUN python scripts/build_rag.py --inputs "endfield_kb/*.jsonl" --reset

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:' + __import__('os').environ.get('PORT', '8000') + '/api/health', timeout=3)"

CMD ["sh", "-c", "python -m uvicorn scripts.api_server:app --host 0.0.0.0 --port ${PORT:-8000}"]
