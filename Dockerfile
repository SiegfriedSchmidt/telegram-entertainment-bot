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
    uv sync --frozen --no-editable

COPY . .

RUN mkdir -p libcpp/build && \
    make -C libcpp

# =====================================================

FROM python:3.14.5-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        dnsutils && \
    rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/main.py /app/
COPY --from=builder /app/lib /app/lib
COPY --from=builder /app/assets /app/assets
COPY --from=builder /app/libcpp /app/libcpp

COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

RUN addgroup --gid 1001 --system app && \
    adduser \
        --uid 1001 \
        --system \
        --group \
        --home /home/app \
        --shell /bin/bash \
        app && \
    mkdir -p /home/app/.config/matplotlib && \
    chown -R app:app /home/app /app

USER app

ENV PATH="/app/.venv/bin:$PATH"

ENV MPLCONFIGDIR=/home/app/.config/matplotlib
ENV SECRET_FOLDER_PATH=/app/secret
ENV DATA_FOLDER_PATH=/app/data
ENV ASSETS_FOLDER_PATH=/app/assets
ENV MIGRATIONS_FOLDER_PATH=/app/migrations

STOPSIGNAL SIGINT

ENTRYPOINT ["/app/.venv/bin/python", "main.py"]
