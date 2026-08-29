# syntax=docker/dockerfile:1
# Isolated development image shared by Codex, Claude Code, and OpenCode. The
# repository is bind-mounted at runtime; no host home directory, Docker
# socket, or browser data is copied in.
#
# Multi-stage so BuildKit can run the independent installs (system apt deps,
# Node + agent CLIs, each npm ci, python deps, AWS CLI) concurrently instead
# of one long chain. `runtime` at the bottom assembles everything with COPY
# --from=. See docker/agent-sandbox/Dockerfile.dockerignore for what build
# context this actually receives — allowlisted to ~700KB of manifests, not
# the whole repo.
FROM python:3.12-slim-bookworm AS base

ENV DEBIAN_FRONTEND=noninteractive

# The base debian image auto-purges downloaded .deb files after every
# install (docker-clean) and disables its own apt cache — both defeat a
# BuildKit cache mount. Undo that once, up front, so apt-get below actually
# reuses the mount across builds instead of re-downloading every time.
RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

# ---------------------------------------------------------------------------
# system: apt packages needed unconditionally (WeasyPrint/ffmpeg deps shared
# with server/Dockerfile, plus the sandbox's own CLI tools). Chromium's own
# libs are NOT here — see the `chromium-libs` stage, only pulled in when
# INSTALL_PLAYWRIGHT_BROWSERS=true.
# ---------------------------------------------------------------------------
FROM base AS system
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
        libcairo2 \
        libffi-dev \
        libgdk-pixbuf-2.0-0 \
        libgirepository1.0-dev \
        gir1.2-pango-1.0 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libpq-dev \
        lsof \
        openssh-client \
        postgresql-client \
        procps \
        redis-tools \
        ripgrep \
        rsync \
        tmux \
        unzip \
        wget

# gh isn't in Debian bookworm main — pull from GitHub's own apt repo, pinned
# by its published signing key, rather than a loose third-party add-apt-repo.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        -o /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update && apt-get install -y --no-install-recommends gh

# ---------------------------------------------------------------------------
# node: pinned Node tarball. Pinned exactly (not "latest-vNN.x") so a routine
# Node patch release doesn't invalidate every downstream layer. Node 22, not
# 20 — @anthropic-ai/claude-code requires Node >=22; vite 7/8 (client/tellus,
# oceanlab) are fine on either, so there's no reason to split versions.
# ---------------------------------------------------------------------------
FROM base AS node
ARG TARGETARCH
ARG NODE_VERSION=22.23.2
# curl/ca-certificates/xz-utils only (xz-utils for `tar -xJf` below, not in
# the base image) — a `system`-sized install here would serialize this stage
# behind it and defeat running them concurrently.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends ca-certificates curl xz-utils
RUN case "${TARGETARCH}" in \
        amd64) node_arch=x64 ;; \
        arm64) node_arch=arm64 ;; \
        *) echo "Unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-${node_arch}.tar.xz" -o /tmp/node.tar.xz \
    && mkdir -p /opt/node \
    && tar -xJf /tmp/node.tar.xz -C /opt/node --strip-components=1 \
    && rm /tmp/node.tar.xz
ENV PATH=/opt/node/bin:${PATH}

# ---------------------------------------------------------------------------
# agents: all three agent CLIs, pinned so a rebuild is reproducible. Bump
# these when intentionally upgrading, not silently on every image build.
# Layered directly on `node` so `runtime` picks up Node + all three CLIs
# with a single COPY --from=agents /opt/node /opt/node.
# ---------------------------------------------------------------------------
FROM node AS agents
ARG CODEX_VERSION=0.150.1
ARG CLAUDE_CODE_VERSION=2.1.243
ARG OPENCODE_VERSION=1.18.22
RUN --mount=type=cache,target=/root/.npm,id=npm-agents \
    npm install --global \
        "@openai/codex@${CODEX_VERSION}" \
        "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" \
        "opencode-ai@${OPENCODE_VERSION}"

# ---------------------------------------------------------------------------
# npm-client: client/ Linux-native node_modules. No native/node-gyp deps in
# this tree (verified against package-lock.json), so this needs Node only —
# not `system`'s gcc/build tooling.
#
# --legacy-peer-deps everywhere below: client/package-lock.json locks
# react@19 while react-simple-maps@3.0.0 peer-requires react<=18. A plain
# `npm ci`/`npm install` on this lockfile fails from scratch on the host too
# (verified) — the checked-in client/node_modules only works because it was
# installed the same way. Pre-existing repo issue, not introduced here.
# ---------------------------------------------------------------------------
FROM node AS npm-client
COPY client/package.json client/package-lock.json /tmp/client/
RUN --mount=type=cache,target=/root/.npm,id=npm-client \
    cd /tmp/client \
    && npm ci --prefer-offline --no-audit --fund=false --legacy-peer-deps \
    && mv node_modules /opt/client-node_modules

# ---------------------------------------------------------------------------
# npm-aux: Tell-Us + Oceanlab node_modules, bundled in one stage since both
# are small relative to client/ and 8GB of builder RAM makes a fourth fully
# concurrent npm/pip stage tight.
# ---------------------------------------------------------------------------
FROM node AS npm-aux
COPY client/tellus/package.json client/tellus/package-lock.json /tmp/tellus/
COPY client/oceanlab/package.json client/oceanlab/package-lock.json /tmp/oceanlab/
RUN --mount=type=cache,target=/root/.npm,id=npm-aux \
    cd /tmp/tellus && npm ci --prefer-offline --no-audit --fund=false --legacy-peer-deps \
    && mv node_modules /opt/tellus-node_modules \
    && cd /tmp/oceanlab && npm ci --prefer-offline --no-audit --fund=false --legacy-peer-deps \
    && mv node_modules /opt/oceanlab-node_modules

# ---------------------------------------------------------------------------
# pydeps: the server's Python venv. FROM `system` (needs gcc/libpq-dev/
# libffi-dev for any dependency without a prebuilt arm64 wheel) rather than
# `base`. `uv` resolves/installs the 52-line requirements.txt considerably
# faster than pip; the venv path below is load-bearing — entrypoint.sh sed's
# this exact string when copying the venv into the runtime volume.
# ---------------------------------------------------------------------------
FROM system AS pydeps
ARG INSTALL_PLAYWRIGHT_BROWSERS=false
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/playwright
COPY server/requirements.txt /tmp/server-requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    --mount=type=cache,target=/root/.cache/uv \
    pip install --no-cache-dir uv \
    && uv venv /opt/bootstrap/server-venv \
    && uv pip install --python /opt/bootstrap/server-venv/bin/python --upgrade pip \
    && uv pip install --python /opt/bootstrap/server-venv/bin/python -r /tmp/server-requirements.txt \
    && uv pip install --python /opt/bootstrap/server-venv/bin/python pytest pytest-asyncio \
    && mkdir -p /opt/playwright \
    && if [ "${INSTALL_PLAYWRIGHT_BROWSERS}" = "true" ]; then \
        /opt/bootstrap/server-venv/bin/python -m playwright install chromium; \
    fi

# ---------------------------------------------------------------------------
# awscli: AWS CLI v2, arch-mapped like the Node tarball above.
# ---------------------------------------------------------------------------
FROM base AS awscli
ARG TARGETARCH
# curl/unzip/ca-certificates only — see the same note in the `node` stage.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    apt-get update && apt-get install -y --no-install-recommends ca-certificates curl unzip
RUN case "${TARGETARCH}" in \
        amd64) aws_arch=x86_64 ;; \
        arm64) aws_arch=aarch64 ;; \
        *) echo "Unsupported architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac \
    && curl -fsSL "https://awscli.amazonaws.com/awscli-exe-linux-${aws_arch}.zip" -o /tmp/awscliv2.zip \
    && unzip -q /tmp/awscliv2.zip -d /tmp \
    && /tmp/aws/install \
    && rm -rf /tmp/aws /tmp/awscliv2.zip

# ---------------------------------------------------------------------------
# runtime: assemble everything above. Only stage that actually needs the
# uid/gid build args and does the final chown/config work.
# ---------------------------------------------------------------------------
FROM system AS runtime

ARG DEPENDENCY_TEMPLATE_ID=legacy

ENV PATH=/opt/node/bin:/usr/local/aws-cli/v2/current/bin:${PATH} \
    PLAYWRIGHT_BROWSERS_PATH=/opt/playwright

# Chromium's own libs (not shared with anything else in `system`), only when
# Playwright's browser is actually wanted. Production's server/Dockerfile
# lets `playwright install --with-deps` pull these; installed explicitly
# here so the default build skips them and the ~150MB libgtk-3-0 pulls in.
ARG INSTALL_PLAYWRIGHT_BROWSERS=false
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    if [ "${INSTALL_PLAYWRIGHT_BROWSERS}" = "true" ]; then \
        apt-get update && apt-get install -y --no-install-recommends \
            libatk-bridge2.0-0 \
            libatk1.0-0 \
            libdrm2 \
            libgbm1 \
            libgtk-3-0 \
            libnspr4 \
            libnss3 \
            libx11-6 \
            libx11-xcb1 \
            libxcb1 \
            libxcomposite1 \
            libxdamage1 \
            libxfixes3 \
            libxkbcommon0 \
            libxrandr2 \
            xdg-utils; \
    fi

COPY --from=agents /opt/node /opt/node
COPY --from=awscli /usr/local/aws-cli /usr/local/aws-cli
COPY --from=awscli /usr/local/bin/aws /usr/local/bin/aws
COPY --from=awscli /usr/local/bin/aws_completer /usr/local/bin/aws_completer

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
COPY --from=pydeps /opt/bootstrap/server-venv /opt/bootstrap/server-venv
COPY --from=pydeps /opt/playwright /opt/playwright
COPY --from=npm-client /opt/client-node_modules /opt/bootstrap/client-node_modules
COPY --from=npm-aux /opt/tellus-node_modules /opt/bootstrap/tellus-node_modules
COPY --from=npm-aux /opt/oceanlab-node_modules /opt/bootstrap/oceanlab-node_modules
COPY server/requirements.txt /tmp/server-requirements.txt
COPY client/package-lock.json /tmp/client/package-lock.json
COPY client/tellus/package-lock.json /tmp/tellus/package-lock.json
COPY client/oceanlab/package-lock.json /tmp/oceanlab/package-lock.json
RUN { \
        sha256sum /tmp/server-requirements.txt /tmp/client/package-lock.json /tmp/tellus/package-lock.json /tmp/oceanlab/package-lock.json; \
        printf '%s\n' 'msandbox-test-tools:pytest,pytest-asyncio:v1'; \
        printf '%s\n' "controller-template:${DEPENDENCY_TEMPLATE_ID}"; \
    } | sha256sum | awk '{print $1}' > /opt/bootstrap/.dependencies-sha \
    && chown -R "${USER_UID}:${USER_GID}" /opt/bootstrap

COPY docker/agent-sandbox/entrypoint.sh /usr/local/bin/agent-sandbox-entrypoint
RUN chmod 0755 /usr/local/bin/agent-sandbox-entrypoint \
    && printf '%s\n' \
        '# Keep the pinned sandbox toolchain visible when agents spawn login shells.' \
        'export PATH="/opt/node/bin:/usr/local/aws-cli/v2/current/bin:$PATH"' \
        > /etc/profile.d/10-msandbox-path.sh \
    && chmod 0644 /etc/profile.d/10-msandbox-path.sh \
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

# Docker Desktop's virtualized Apple-silicon CPU can advertise ARM crypto
# capabilities that cryptography's bundled OpenSSL cannot safely execute,
# causing AES setup to terminate Python with SIGILL. Disable that runtime
# autodetection only in this local sandbox; real production ARM hosts are not
# affected by the Docker Desktop virtualization issue.
ENV OPENSSL_armcap=0

WORKDIR /workspace
ENTRYPOINT ["/usr/local/bin/agent-sandbox-entrypoint"]
CMD ["sleep", "infinity"]
