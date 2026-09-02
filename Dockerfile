FROM python:3.14.5-slim AS builder

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_PYTHON_DOWNLOADS=0 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        make \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY pyproject.toml uv.lock ./

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-editable --no-dev

COPY . .

RUN mkdir -p libcpp/build && \
    make -C libcpp

# =====================================================
# FINAL STAGE
# =====================================================
FROM python:3.14.5-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# 1. Install runtime dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        dnsutils && \
    rm -rf /var/lib/apt/lists/*

# 2. Create user and group FIRST (before copying app files)
RUN addgroup --gid 1001 --system app && \
    adduser --uid 1001 --system --group --home /home/app --shell /bin/bash app && \
    mkdir -p /home/app/.config/matplotlib && \
    chown -R app:app /home/app

# 3. Copy files WITH --chown to avoid layer duplication
COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --from=builder --chown=app:app /app/main.py /app/
COPY --from=builder --chown=app:app /app/lib /app/lib
COPY --from=builder --chown=app:app /app/assets /app/assets
COPY --from=builder --chown=app:app /app/libcpp /app/libcpp

# Deno binary (root ownership is fine here since it's in /usr/local/bin and executable)
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

USER app

ENV PATH="/app/.venv/bin:$PATH"
ENV MPLCONFIGDIR=/home/app/.config/matplotlib
ENV SECRET_FOLDER_PATH=/app/secret
ENV DATA_FOLDER_PATH=/app/data
ENV ASSETS_FOLDER_PATH=/app/assets
ENV MIGRATIONS_FOLDER_PATH=/app/migrations

STOPSIGNAL SIGINT

ENTRYPOINT ["/app/.venv/bin/python", "main.py"]
