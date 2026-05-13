FROM python:3.13.2-slim AS builder

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        make \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Prepare requirements
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

# Build libcpp
COPY libcpp ./libcpp
RUN mkdir -p libcpp/build && \
    make -C libcpp

FROM denoland/deno:bin AS deno

FROM python:3.13.2-slim

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

RUN apt-get update -qq && \
    apt-get install -y --no-install-recommends \
        ffmpeg \
        ca-certificates \
        dnsutils && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache-dir /wheels/* && \
    rm -rf /wheels

COPY --from=builder /app/libcpp/build /app/libcpp/build
COPY --from=deno /deno /usr/local/bin/deno

#RUN addgroup --gid 1001 --system app && \
#    adduser --no-create-home --shell /bin/false --disabled-password --uid 1001 --system --group app

RUN addgroup --gid 1001 --system app && \
    adduser --uid 1001 --system --group --home /home/app --shell /bin/bash app && \
    mkdir -p /home/app/.config/matplotlib && \
    chown -R app:app /home/app

USER app
STOPSIGNAL SIGINT

ENV MPLCONFIGDIR=/home/app/.config/matplotlib
ENV SECRET_FOLDER_PATH=/app/secret
ENV DATA_FOLDER_PATH=/app/data
ENV ASSETS_FOLDER_PATH=/app/assets
ENV MIGRATIONS_FOLDER_PATH=/app/migrations

COPY . /app
ENTRYPOINT ["python3", "main.py"]
