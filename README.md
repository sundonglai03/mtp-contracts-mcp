# mtp-contracts-mcp

Streamable HTTP MCP 服务：校验调用者给出的多个 JSON 测试用例，并在全部合法时返回一个 JSON 套件对象。

它不读取文件、不解析 YAML、不执行测试、不调用大模型，也不会补写业务步骤。

## 快速启动

```bash
docker compose up -d --build
```

- MCP：`http://<服务器IP>:8000/mcp`

可选地设置访问令牌：

```bash
export MTP_CONTRACTS_MCP_TOKEN='替换为随机长字符串'
docker compose up -d --build
```

设置后，访问 `/mcp` 必须附带 `Authorization: Bearer <token>`。

## 唯一工具：`build_suite`

工具只接受一个 JSON 参数对象，其中 `cases` 必填且必须是非空数组。每个元素必须是 JSON 对象：

```json
{
  "cases": [
    {
      "id": "login-success",
      "title": "正常登录",
      "steps": [
        {"id": "open", "action": "playwright.navigate", "args": {"url": "https://example.test/login"}}
      ]
    }
  ]
}
```

不接收文件路径、YAML 文本或字符串形式的用例。仅当用例缺少 `schema_version` 时补默认值 `1`；其他字段和业务步骤不推断、不改写。套件内的 `id` 必须唯一。

校验依据 `mtp-contracts-core` 的**共用动作目录**（`mtp_contracts.action_catalog`），与平台上传校验是同一份：未知 action、缺必填参数、参数类型不符、重复 id、引用不存在的步骤、引用某步骤不会返回的字段都会报出来。`errors[].code` 是问题码（`unknown_action` / `missing_arg` / `invalid_arg_type` / `unknown_result_field`，通用结构问题仍是 `schema` / `semantics`）。本服务的 instructions 里的动作清单由该目录生成，不手写。

无论校验成功或失败，工具均返回同一 JSON 结构：

```json
{
  "ok": true,
  "suite": {"cases": [{"schema_version": 1, "id": "login-success", "title": "正常登录", "steps": [{"id": "open", "action": "playwright.navigate"}]}]},
  "errors": []
}
```

任一用例不合法时，`ok` 为 `false`、`suite` 为 `null`，绝不返回半成品：

```json
{
  "ok": false,
  "suite": null,
  "errors": [
    {
      "case_index": 1,
      "case_id": "login-failure",
      "path": "steps",
      "code": "schema",
      "message": "缺少必填字段"
    }
  ]
}
```

每个错误对象始终只有以下字段：`case_index`、`case_id`、`path`、`code`、`message`。

## 环境变量

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `MTP_CONTRACTS_MCP_HOST` | `127.0.0.1` | 监听地址 |
| `MTP_CONTRACTS_MCP_PORT` | `8000` | 监听端口 |
| `MTP_CONTRACTS_MCP_ALLOWED_HOSTS` | 仅本机 | Host 白名单，逗号分隔；`off` 表示关闭校验 |
| `MTP_CONTRACTS_MCP_TOKEN` | 空 | Bearer Token；为空时不启用认证 |

## Agent 集成（skill）

仓库自带一个 skill：`.codebuddy/skills/mtp-contracts-mcp/`。

| 文件 | 作用 |
| --- | --- |
| `SKILL.md` | 何时调用、工具契约、修错重试流程、硬性约束与常见错误码 |
| `references/case-schema.md` | 用例 / 步骤 / 断言 / fixture 字段表、内置 action 清单、变量与证据约定、完整示例 |
| `scripts/build_suite.py` | 命令行校验：读 `cases.json` 调 `build_suite`，成功写出 `suite.json`（退出码 0 / 1 / 2） |

以本仓库为工作区打开时，CodeBuddy 会自动加载它（项目级 `.codebuddy/skills/`）。
要让它在所有工作区都可用，拷到用户级目录即可：

```bash
mkdir -p ~/.codebuddy/skills
cp -r .codebuddy/skills/mtp-contracts-mcp ~/.codebuddy/skills/
```

不配 MCP 客户端也能用脚本单独校验：

```bash
uv run --quiet --with "mcp>=2.0" \
  .codebuddy/skills/mtp-contracts-mcp/scripts/build_suite.py cases.json --out suite.json
```

## 验证

```bash
uv run --frozen --extra dev pytest -q
docker compose config
```
