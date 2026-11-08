FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Seoul
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir .
COPY migrations/ migrations/
COPY config/ config/
RUN useradd -m -u 10001 noa && mkdir -p /app/data/raw /app/artifacts \
    && chown -R noa:noa /app
USER noa
HEALTHCHECK --interval=1m --timeout=10s --start-period=2m --retries=3 \
    CMD python -c "import os,time; p='/tmp/noa_pipeline_heartbeat'; assert os.path.isfile(p) and time.time()-os.path.getmtime(p)<180"
CMD ["python", "-m", "noa_data.pipeline_service"]
