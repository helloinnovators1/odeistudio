FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    ENVIRONMENT=production

WORKDIR /app

RUN groupadd --system --gid 10001 odei \
    && useradd --system --uid 10001 --gid odei --home-dir /nonexistent \
       --shell /usr/sbin/nologin odei

COPY pyproject.toml ./
COPY odei_api ./odei_api

RUN python -m pip install --no-cache-dir .

USER 10001:10001
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/live', timeout=2)"]

ENTRYPOINT ["python", "-m", "uvicorn", "odei_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
