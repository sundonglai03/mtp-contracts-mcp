---
name: mtp-contracts-mcp
description: This skill should be used when authoring, fixing, or validating MTP JSON test suites — the cases JSON that mtp-platform executes — or whenever a task requires calling the mtp-contracts-mcp service, whose single build_suite tool is served over Streamable HTTP on port 8000. It covers the tool contract, the case/step/assertion schema, the fix-and-retry loop on validation errors, and how to hand the validated suite to mtp-platform.
---

# MTP 用例套件构建与校验

## 用途

把「一组 JSON 测试用例」交给 `mtp-contracts-mcp` 的 `build_suite` 工具做**唯一入口校验**；
只有返回 `ok: true` 时，才把 `suite.cases` 提交给 `mtp-platform` 执行。

服务**只校验**：不读文件、不解析 YAML、不执行测试、不调模型、不补写业务步骤
（唯一的补全是给缺失的 `schema_version` 补 `1`）。

## 何时使用

- 需要新建或修改 MTP 测试用例 JSON（`steps` / `assertions` / `secrets`）时；
- 需要在提交到 mtp-platform 之前确认用例合法时；
- 校验失败后要按错误路径定位并修正时。

## 服务契约

| 项 | 值 |
| --- | --- |
| 端点 | `http://<host>:8000/mcp`（Streamable HTTP；内网部署默认 `192.168.11.231:8000`） |
| 认证 | 可选。服务端设了 `MTP_CONTRACTS_MCP_TOKEN` 时，请求需带 `Authorization: Bearer <token>` |
| 工具 | **只有** `build_suite`，不要假设或调用其他工具 |
| 入参 | `{"cases": [<用例对象>, ...]}`；`cases` 必填、非空数组 |
| 返回 | `{"ok": bool, "suite": {"cases": [...]} \| null, "errors": [...]}` |

两个必须记住的实测事实：

1. **校验失败也是「正常返回」**：MCP 结果的 `is_error`（`isError`）始终为 `false`，
   必须解析返回体里的 `ok` 来判断成功与否。
2. 返回体同时出现在 `structured_content`（JSON 对象）和 `content[0].text`（同一份 JSON 的字符串）中，
   两者内容一致，取任意一个即可。

调用方式（二选一）：

- 已在 MCP 客户端注册该服务时，直接调用工具：
  ```json
  {"mcpServers": {"mtp-contracts": {"type": "http", "url": "http://192.168.11.231:8000/mcp"}}}
  ```
  （`type` 字段名随客户端而异，可能是 `http` / `streamableHttp`；带 Token 时加
  `"headers": {"Authorization": "Bearer <token>"}`。）
- 没有 MCP 客户端时，用本 skill 的脚本（路径相对仓库根；若 skill 装在用户级目录，
  把路径换成 `~/.codebuddy/skills/mtp-contracts-mcp/scripts/build_suite.py`）：
  ```bash
  uv run --quiet --with "mcp>=2.0" \
    .codebuddy/skills/mtp-contracts-mcp/scripts/build_suite.py cases.json --out suite.json
  ```

## 工作流（按序执行）

1. **组用例**：在本地写成 JSON（字段与示例见 `references/case-schema.md`）。
   不要传文件路径、YAML/Markdown、JSON 字符串，也不要包一层 `{"suite": {...}}`。
2. **校验**：调用 `build_suite`（或上面的脚本）。
3. **失败就改**：按每条 `errors[].path` + `code` + `message` 修正本地 JSON，然后重新校验。
   **不要**提交半成品、绕过校验，或自行假定已通过。
4. **成功才交付**：`ok: true` 时把 `suite.cases` 交给 mtp-platform
   （Web 界面：新建任务上传该 JSON 文件；或 API：`POST /api/runs`，两者都需要已登录）。
5. **执行后看结果**：任务详情 → 用例 → 步骤；截图证据在对应步骤下内联显示。

## 硬性约束（违反会被拒）

- `cases` 必须是非空数组，每项必须是 JSON 对象；**同一次调用内用例 `id` 必须唯一**。
- 用例必填：`schema_version`（必须为 `1`）、`id`、`title`、`steps`（至少 1 个）。
- 步骤必填：`id`、`action`（`<适配器>.<动作>`，如 `playwright.navigate`）。
- 断言必填：`type`；顶层断言还必须给 `id`，且同用例内唯一。
- **所有对象都是 `additionalProperties: false`**：多写一个 schema 里没定义的字段就会报
  `schema` 错误。不确定的字段不要写。
- `id` 格式：用例 `^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$`（允许点），
  步骤/断言 `^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`（**不允许点**）。
- 变量引用必须落在已声明的命名空间里（`env` / `vars` / `secrets` / `steps` / `run` / `now`）；
  引用不存在的步骤 id 或未声明的变量会被语义校验拦下。
- 测试凭证写在用例的 `secrets` 里，用 `{{ secrets.xxx }}` 引用；平台配置与 tools 不保存凭证。
- Playwright 的 `args.target` 必须是真实可执行的 CSS / Playwright selector，
  不能写「跳过」「某行的勾选框」这类自然语言描述。

## 错误码与修法

`errors[]` 每项固定只有 `case_index` / `case_id` / `path` / `code` / `message` 五个字段。

| code | 含义 | 修法 |
| --- | --- | --- |
| `required` | 缺必填字段（`path` 指出是哪个） | 补上该字段；用例至少要有 `steps` 且非空 |
| `schema` | 字段类型/取值不符，或写了未定义的字段 | 按 `path` 改；对照 `references/case-schema.md` 删掉多余字段 |
| `duplicate_id` | 用例 `id` 重复 | 改 `id`（消息里会指出与哪一项重复） |
| `semantics` | 语义问题：不支持 `schema_version`、步骤/断言 id 重复、变量引用越界 | 按消息里的「已声明: ...」列表修正引用或补声明 |
| `invalid_cases_type` / `empty_cases` / `invalid_case_type` | 入参形状不对 | 传非空数组，每项是 JSON 对象 |

## 写用例时最容易踩的两点

1. **用例 id 与步骤 id 的字符集不同**：用例 id 可带点（`TC_bypass.1`），步骤 id 不能带点。
2. **截图证据只在宏观步骤声明**：在业务上「一个重要步骤」的收尾那一步写
   `"evidence": ["screenshot"]` 即可（不要给「打开浏览器、点导航」这类技术步骤都加）。
   浏览器步骤失败时平台会自动补一张截图；`snapshot` / `console` / `network` 当前同样按截图处理，
   ssh / mysql / api 步骤不采集证据。

## 参考文件

- `references/case-schema.md`：用例 / 步骤 / 断言 / fixture 的完整字段表、内置 action 清单、
  变量命名空间、可直接复制的完整示例。
- `scripts/build_suite.py`：命令行调用 `build_suite`（打印 `ok` 与错误，成功时写出 `suite.json`），
  适合没有 MCP 客户端的场景；退出码 `0`=校验通过、`1`=用例不合法、`2`=调用失败。
