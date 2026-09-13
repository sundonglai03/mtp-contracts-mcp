# mtp-contracts-mcp

**测试用例规范系统**：把 `contracts-core` 暴露为一个 **Streamable HTTP MCP 服务**，供 Agent、Codex、n8n 及其他客户端复用。

它**不是测试执行器**：不连 SSH / MySQL / 浏览器，不跑用例，不生成报告，不持有目标系统凭据。

## 职责

把不同来源（DOCX、功能点、自然语言、不规范 YAML）的用例**转换、校验、规范化为统一格式**。

暴露的 MCP 工具（第一版只做确定性工具，不调用大模型）：

| 工具 | 作用 |
|---|---|
| `validate_case` | 校验单个用例，返回全部问题（带字段路径） |
| `validate_suite` | 校验一组用例，汇总结果 |
| `normalize_case` | 把候选用例规范化为标准格式 |
| `get_schema` | 返回用例 JSON Schema 与支持的 schema_version |
| `explain_validation_error` | 把错误路径翻译成人能看懂的解释与修复建议 |

## 依赖

- 上游：`mtp-contracts`（**同一个契约实现**，不复制校验逻辑）
- 下游：无（它是被复用的服务）

## 本地构建 / 安装

`mtp-contracts` 是固定版本依赖，需先构建其 wheel 再装本包：

```bash
# 1) 先构建上游 contracts wheel
(cd ../mtp-contracts && .venv/bin/python -m pip wheel . -w dist --no-deps)

# 2) 建 venv 并按固定版本安装本包
python -m venv .venv
.venv/bin/pip install -e ".[dev]" --find-links ../mtp-contracts/dist
.venv/bin/python -m pytest -q
```

## 运行（Streamable HTTP）

```bash
.venv/bin/mtp-contracts-mcp --host 0.0.0.0 --port 8000
# MCP 端点： http://<host>:8000/mcp
```

两个系统**分开部署**，各自维护 Dockerfile / compose / 环境变量 / healthcheck / CI。
