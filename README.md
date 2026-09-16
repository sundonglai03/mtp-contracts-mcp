# mtp-contracts-mcp

把自然语言或候选测试用例转换、校验为统一格式的 Streamable HTTP MCP 服务。

它只负责测试用例规范，不连接 SSH、MySQL 或浏览器，也不执行测试和保存目标系统凭据。

## 快速启动

### Docker

```bash
docker compose up -d --build
docker compose logs -f contracts-mcp
```

- MCP：`http://<服务器IP>:8000/mcp`
- 健康检查：`http://<服务器IP>:8000/health`
- 镜像：`mtp-contracts-mcp:0.1.0`
- 容器：`mtp-contracts-mcp`

内网使用也建议设置访问令牌：

```bash
export MTP_CONTRACTS_MCP_TOKEN='替换为随机长字符串'
docker compose up -d --build
```

设置后，访问 `/mcp` 必须携带：

```http
Authorization: Bearer 替换为随机长字符串
```

`/health` 不需要令牌。

### 本地运行

```bash
uv sync --frozen --extra dev
uv run --frozen mtp-contracts-mcp --host 0.0.0.0 --port 8000
```

## 提供的工具

| 工具 | 作用 |
| --- | --- |
| `normalize_case` | 保守地把候选内容转换为标准用例 |
| `validate_case` | 校验单个用例并返回字段路径和全部问题 |
| `validate_suite` | 批量校验一组用例 |
| `get_schema` | 返回 JSON Schema 和支持的版本 |
| `explain_validation_error` | 将校验错误转换为可读说明和修复建议 |

这些工具都是确定性工具：不调用大模型，也不负责补写测试业务内容。Agent 负责理解需求和生成候选用例，本服务负责规范化和把关。

## 典型流程

```text
需求 / 功能点 / 原始用例
        ↓
       Agent
        ↓ 调用 MCP
规范化用例 + 校验结果
        ↓
   mtp-platform 执行
```

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MTP_CONTRACTS_MCP_HOST` | `127.0.0.1` | 监听地址 |
| `MTP_CONTRACTS_MCP_PORT` | `8000` | 监听端口 |
| `MTP_CONTRACTS_MCP_ALLOWED_HOSTS` | 仅本机 | Host 白名单，逗号分隔；`off` 表示关闭校验 |
| `MTP_CONTRACTS_MCP_TOKEN` | 空 | Bearer Token；为空时不启用认证 |

Compose 为方便内网访问设置了 `MTP_CONTRACTS_MCP_ALLOWED_HOSTS=off`。跨不可信网络时，应启用令牌，并在反向代理上配置 HTTPS 和明确的 Host 白名单。

## contracts 维护

契约源码位于 `src/mtp_contracts_mcp/contracts/`，它是唯一事实来源。修改后同步到相邻的 `mtp-platform`：

```bash
uv run --frozen python scripts/sync_contracts.py
```

`_sync_manifest.json` 和 `tests/test_contracts_integrity.py` 用于发现两个项目之间的契约漂移。

## 验证

```bash
uv run --frozen --extra dev pytest -q
docker compose config
```
