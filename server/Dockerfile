# syntax=docker/dockerfile:1
# Stage 1: Base image with system dependencies
FROM --platform=linux/arm64 python:3.12-slim-bookworm AS base

# Install system dependencies (including WeasyPrint requirements)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    libcairo2 \
    libgirepository1.0-dev \
    gir1.2-pango-1.0 \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Stage 2: Dependencies installation
FROM base AS dependencies

WORKDIR /app

# Copy only requirements first for layer caching
COPY requirements.txt .

# Install Python dependencies with BuildKit cache mount
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# Stage 3: Runtime image
FROM base AS runtime

WORKDIR /app

# Copy Python dependencies from dependencies stage
COPY --from=dependencies /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# Create non-root user
RUN groupadd -r matcha && useradd -r -g matcha matcha

# Create uploads directory
RUN mkdir -p /app/uploads && chown -R matcha:matcha /app/uploads

# Copy application code
COPY . .

# Pre-compile Python bytecode for faster startup
RUN python -m compileall -q -x "test" . || true

# Set ownership
RUN chown -R matcha:matcha /app

# Switch to non-root user
USER matcha

# Expose port
EXPOSE 8002

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8002/health')" || exit 1

# Start application with production settings (2 workers for memory efficiency)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002", "--workers", "2", "--loop", "asyncio"]
