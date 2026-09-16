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

# 先装依赖（利用层缓存）
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --no-dev --frozen --no-install-project

# 再装本包源码
COPY src ./src
RUN uv sync --no-dev --frozen

ENV PATH="/app/.venv/bin:$PATH" \
    MTP_CONTRACTS_MCP_HOST=0.0.0.0 \
    MTP_CONTRACTS_MCP_PORT=8000
EXPOSE 8000

# slim 镜像没有 curl，用 python 探活
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health').status==200 else 1)"

ENTRYPOINT ["mtp-contracts-mcp"]
CMD ["--host", "0.0.0.0", "--port", "8000"]
