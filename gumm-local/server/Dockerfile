# syntax=docker/dockerfile:1
FROM --platform=linux/arm64 python:3.12-slim-bookworm AS base

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

FROM base AS dependencies

WORKDIR /app
COPY requirements.txt .

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt

FROM base AS runtime

WORKDIR /app

COPY --from=dependencies /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

RUN groupadd -r gummlocal && useradd -r -g gummlocal gummlocal

COPY . .
RUN python -m compileall -q -x "test" . || true
RUN chown -R gummlocal:gummlocal /app

USER gummlocal

EXPOSE 8004

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8004/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004", "--workers", "2", "--loop", "asyncio"]
