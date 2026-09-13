# mtp-contracts-mcp

**测试用例规范系统**：把 **contracts-core** 暴露为一个 **Streamable HTTP MCP 服务**，
供 Agent、Codex、n8n 及其他客户端复用。

它**不是测试执行器**：不连 SSH / MySQL / 浏览器，不跑用例，不生成报告，不持有目标系统凭据。

## 职责

把不同来源（DOCX、功能点、自然语言、不规范 YAML）的用例**校验、规范化**为统一格式。

暴露的 MCP 工具（均为确定性工具，不调用大模型、不执行测试）：

| 工具 | 作用 |
|---|---|
| `validate_case` | 校验单个用例，返回全部问题（带字段路径） |
| `validate_suite` | 校验一组用例，汇总结果 |
| `normalize_case` | 把候选用例规范化为标准格式（保守、可解释） |
| `get_schema` | 返回用例 JSON Schema 与支持的 schema_version |
| `explain_validation_error` | 把错误路径翻译成人能看懂的说明与修复建议 |

## contracts-core 内联（必读）

contracts-core 在本项目内是一份**内联副本**（`src/mtp_contracts_mcp/contracts/`），与
`mtp-platform` 里的那份**逐字节一致**。

- **唯一事实来源是 `mtp-platform`**：要改 contracts，在那边改，然后运行任一项目的
  `uv run python scripts/sync_contracts.py` 同步过来。
- 副本带 `_sync_manifest.json`；`tests/test_contracts_integrity.py` 检测漂移。

## 技术栈

基于 **mcp 2.x**（`mcp.server.mcpserver.MCPServer`，注意 1.x 的 `FastMCP` 已改名）。
Streamable HTTP 端点默认 `/mcp`，另提供免鉴权的 `/health` 供容器探活。

Host 白名单（DNS-rebinding 防护）由环境变量控制：

| 变量 | 说明 |
|---|---|
| `MTP_CONTRACTS_MCP_HOST` | 监听地址，默认 `127.0.0.1` |
| `MTP_CONTRACTS_MCP_PORT` | 监听端口，默认 `8000` |
| `MTP_CONTRACTS_MCP_ALLOWED_HOSTS` | 允许的 Host（逗号分隔，支持 `host:*`）；设为 `off` 关闭校验。默认只放行本机，容器/内网访问需设置 |

## 本地开发（uv）

```bash
uv sync --extra dev
uv run pytest -q                       # 含 ASGI 进程内协议级端到端
uv run mtp-contracts-mcp --host 0.0.0.0 --port 8000
# MCP 端点： http://<host>:8000/mcp   ；探活： /health
```

## 容器部署（独立 compose）

```bash
docker compose up --build          # 端口 8000
```

两个系统**各自独立**部署，不共用 compose。
