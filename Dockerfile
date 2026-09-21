FROM python:3.12-slim

ARG UV_VERSION=0.12.5
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir "uv==$UV_VERSION"

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    UV_CACHE_DIR=/app/.cache/uv

# 先装依赖（利用层缓存）
# 依赖缓存挂在当前目录下的 /app/.cache/uv（见上面的 UV_CACHE_DIR）：
# 依赖层重建（uv.lock 变更、换构建机、清过层缓存）时不会回 PyPI 重下，
# git 依赖也不需要重新 clone。
COPY pyproject.toml uv.lock README.md ./
RUN --mount=type=cache,target=/app/.cache/uv \
    uv sync --no-dev --frozen --no-install-project

# 再装本包源码
COPY src ./src
RUN --mount=type=cache,target=/app/.cache/uv \
    uv sync --no-dev --frozen

ENV PATH="/app/.venv/bin:$PATH" \
    MTP_CONTRACTS_MCP_HOST=0.0.0.0 \
    MTP_CONTRACTS_MCP_PORT=8000
EXPOSE 8000

ENTRYPOINT ["mtp-contracts-mcp"]
CMD ["--host", "0.0.0.0", "--port", "8000"]
