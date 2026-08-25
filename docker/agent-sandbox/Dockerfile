# syntax=docker/dockerfile:1
# Isolated development image shared by Codex, Claude Code, and OpenCode. The
# repository is bind-mounted at runtime; no host home directory, Docker
# socket, or browser data is copied in.
FROM python:3.12-slim-bookworm

ARG INSTALL_PLAYWRIGHT_BROWSERS=false

ENV DEBIAN_FRONTEND=noninteractive \
    PATH=/opt/node/bin:/usr/local/aws-cli/v2/current/bin:${PATH} \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

# The base debian image auto-purges downloaded .deb files after every
# install (docker-clean) and disables its own apt cache — both defeat a
# BuildKit cache mount. Undo that once, up front, so apt-get below actually
# reuses the mount across builds instead of re-downloading every time.
RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        fonts-dejavu-core \
        gcc \
        git \
        gosu \
        jq \
        less \
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
        openssh-client \
        postgresql-client \
        procps \
        redis-tools \
        ripgrep \
        rsync \
        tmux \
        unzip \
        wget \
        xdg-utils

# gh isn't in Debian bookworm main — pull from GitHub's own apt repo, pinned
# by its published signing key, rather than a loose third-party add-apt-repo.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh

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
    && rm /tmp/node.tar.xz

# All three agent CLIs, pinned so a rebuild is reproducible. Bump these when
# intentionally upgrading, not silently on every image build.
ARG CODEX_VERSION=0.149.1
ARG CLAUDE_CODE_VERSION=2.1.243
ARG OPENCODE_VERSION=1.18.22
RUN --mount=type=cache,target=/root/.npm \
    npm install --global \
        "@openai/codex@${CODEX_VERSION}" \
        "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
        "opencode-ai@${OPENCODE_VERSION}"

# AWS CLI v2, arch-mapped like the Node tarball above.
RUN case "${TARGETARCH}" in \
        amd64) aws_arch=x86_64 ;; \
        arm64) aws_arch=aarch64 ;; \
        *) echo "Unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-${aws_arch}.zip" -o /tmp/awscliv2.zip \
    && unzip -q /tmp/awscliv2.zip -d /tmp \
    && /tmp/aws/install \
    && rm -rf /tmp/aws /tmp/awscliv2.zip

# uid/gid default to the host user (macOS finch:staff) so files the agent
# writes through the bind mount, and 0400 secrets like the SSH key, keep
# working ownership/permissions on both sides. gid 20 already exists in
# Debian as "dialout" — only create the group if that id is free.
ARG USER_UID=501
ARG USER_GID=20
RUN if ! getent group "${USER_GID}" >/dev/null; then groupadd --gid "${USER_GID}" agent; fi \
    && useradd --uid "${USER_UID}" --gid "${USER_GID}" --create-home --shell /bin/bash agent \
    && mkdir -p /workspace /opt/bootstrap

# Bake Linux-native dependency trees into the image, then copy them into named
# volumes on first start. This prevents macOS node_modules and virtualenvs from
# being reused by the container.
COPY server/requirements.txt /tmp/server-requirements.txt
COPY client/package.json client/package-lock.json /tmp/client/
COPY client/tellus/package.json client/tellus/package-lock.json /tmp/tellus/
COPY client/oceanlab/package.json client/oceanlab/package-lock.json /tmp/oceanlab/
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/root/.npm \
    python -m venv /opt/bootstrap/server-venv \
    && /opt/bootstrap/server-venv/bin/pip install --upgrade pip \
    && /opt/bootstrap/server-venv/bin/pip install -r /tmp/server-requirements.txt \
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
    && chown -R "${USER_UID}:${USER_GID}" /opt/bootstrap

COPY docker/agent-sandbox/entrypoint.sh /usr/local/bin/agent-sandbox-entrypoint
RUN chmod 0755 /usr/local/bin/agent-sandbox-entrypoint \
    && mkdir -p \
        /home/agent/.config/git \
        /home/agent/.config/opencode \
        /home/agent/.cache \
        /home/agent/.npm \
    && chown -R "${USER_UID}:${USER_GID}" /home/agent

# OpenCode's own permission model is redundant once the container is the
# security boundary — allow everything so it behaves like Codex's
# --dangerously-bypass-approvals-and-sandbox and Claude's
# --dangerously-skip-permissions.
RUN printf '%s\n' \
        '{"$schema":"https://opencode.ai/config.json","permission":{"edit":"allow","bash":"allow","webfetch":"allow"}}' \
        > /home/agent/.config/opencode/opencode.json \
    && chown "${USER_UID}:${USER_GID}" /home/agent/.config/opencode/opencode.json

WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/agent-sandbox-entrypoint"]
CMD ["sleep", "infinity"]
