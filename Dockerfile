FROM python:3.11-slim

# Non-root user: if the app is ever compromised it cannot modify the system.
RUN useradd --create-home --uid 1000 appuser
ENV HF_HOME=/home/appuser/.cache/huggingface \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /home/appuser/app

# CPU-only PyTorch (~200 MB) instead of the default CUDA build (~2 GB): we have no GPU.
COPY requirements.txt .
RUN pip install torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install -r requirements.txt

USER appuser

# Download both models at BUILD time so the container starts fast and works offline.
RUN python -c "from sentence_transformers import SentenceTransformer, CrossEncoder; \
SentenceTransformer('BAAI/bge-small-en-v1.5'); \
CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')"

COPY --chown=appuser:appuser app app
COPY --chown=appuser:appuser data/index data/index
COPY --chown=appuser:appuser data/processed data/processed
COPY --chown=appuser:appuser eval eval

EXPOSE 7860
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:7860/health')"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860"]
