# syntax=docker/dockerfile:1
# Isolated development image for the Codex CLI. The repository is bind-mounted
# at runtime; no host home directory, Docker socket, or browser data is copied.
FROM python:3.12-slim-bookworm

ARG INSTALL_PLAYWRIGHT_BROWSERS=false

ENV DEBIAN_FRONTEND=noninteractive \
    PATH=/opt/node/bin:${PATH} \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        fonts-dejavu-core \
        gcc \
        gh \
        git \
        gosu \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libcairo2 \
        libdrm2 \
        libffi-dev \
        libgbm1 \
        libgdk-pixbuf-2.0-0 \
        libgirepository1.0-dev \
        gir1.2-pango-1.0 \
        libgtk-3-0 \
        libnspr4 \
        libnss3 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libpq-dev \
        libx11-6 \
        libx11-xcb1 \
        libxcb1 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxkbcommon0 \
        libxrandr2 \
        lsof \
        postgresql-client \
        redis-tools \
        rsync \
        tmux \
        wget \
        xdg-utils \
        && rm -rf /var/lib/apt/lists/*

# Node 20 is installed from the official tarball so this image can keep the
# Python 3.12 base while avoiding a host Node installation.
ARG TARGETARCH
RUN case "${TARGETARCH}" in \
        amd64) node_arch=x64 ;; \
        arm64) node_arch=arm64 ;; \
        *) echo "Unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && node_file="$(curl -fsSL https://nodejs.org/dist/latest-v20.x/SHASUMS256.txt | awk -v arch="$node_arch" '$2 ~ ("node-v.*-linux-" arch "\\.tar\\.xz$") {print $2; exit}')" \
    && test -n "$node_file" \
    && curl -fsSL "https://nodejs.org/dist/latest-v20.x/${node_file}" -o /tmp/node.tar.xz \
    && mkdir -p /opt/node \
    && tar -xJf /tmp/node.tar.xz -C /opt/node --strip-components=1 \
    && rm /tmp/node.tar.xz \
    && npm install --global @openai/codex

RUN groupadd --gid 1000 codex \
    && useradd --uid 1000 --gid codex --create-home --shell /bin/bash codex \
    && mkdir -p /workspace /opt/bootstrap

# Bake Linux-native dependency trees into the image, then copy them into named
# volumes on first start. This prevents macOS node_modules and virtualenvs from
# being reused by the container.
COPY server/requirements.txt /tmp/server-requirements.txt
COPY client/package.json client/package-lock.json /tmp/client/
COPY client/tellus/package.json client/tellus/package-lock.json /tmp/tellus/
COPY client/oceanlab/package.json client/oceanlab/package-lock.json /tmp/oceanlab/
RUN python -m venv /opt/bootstrap/server-venv \
    && /opt/bootstrap/server-venv/bin/pip install --no-cache-dir --upgrade pip \
    && /opt/bootstrap/server-venv/bin/pip install --no-cache-dir -r /tmp/server-requirements.txt \
    && cd /tmp/client && npm ci \
    && mv /tmp/client/node_modules /opt/bootstrap/client-node_modules \
    && cd /tmp/tellus && npm ci \
    && mv /tmp/tellus/node_modules /opt/bootstrap/tellus-node_modules \
    && cd /tmp/oceanlab && npm ci \
    && mv /tmp/oceanlab/node_modules /opt/bootstrap/oceanlab-node_modules \
    && sha256sum /tmp/server-requirements.txt /tmp/client/package-lock.json /tmp/tellus/package-lock.json /tmp/oceanlab/package-lock.json \
        | sha256sum | awk '{print $1}' > /opt/bootstrap/.dependencies-sha \
    && if [ "${INSTALL_PLAYWRIGHT_BROWSERS}" = "true" ]; then \
        /opt/bootstrap/server-venv/bin/python -m playwright install chromium; \
    fi \
    && chown -R codex:codex /opt/bootstrap

COPY docker/codex-sandbox/entrypoint.sh /usr/local/bin/codex-sandbox-entrypoint
RUN chmod 0755 /usr/local/bin/codex-sandbox-entrypoint \
    && mkdir -p /home/codex/.config/git /home/codex/.cache /home/codex/.npm \
    && chown -R codex:codex /home/codex

WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/codex-sandbox-entrypoint"]
CMD ["sleep", "infinity"]
