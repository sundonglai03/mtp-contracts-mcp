FROM python:3.12-slim

ARG UV_VERSION=0.12.5
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "uv==$UV_VERSION"

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# 先装依赖（利用层缓存）：只 COPY 锁文件，改 src 不会触发重装。
# 构建机装了 buildx（Docker 23+ 自带，或 docker-buildx-plugin）后，可以给这两条
# RUN 加上 --mount=type=cache,target=/root/.cache/uv，让锁文件变更后的重装也复用
# 宿主机缓存，不必重新下载 wheel 和 clone git 依赖。
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --frozen --no-install-project

# 再装本包源码
COPY src ./src
RUN uv sync --no-dev --frozen

ENV PATH="/app/.venv/bin:$PATH" \
    MTP_CONTRACTS_MCP_HOST=0.0.0.0 \
    MTP_CONTRACTS_MCP_PORT=8000
EXPOSE 8000

ENTRYPOINT ["mtp-contracts-mcp"]
CMD ["--host", "0.0.0.0", "--port", "8000"]
