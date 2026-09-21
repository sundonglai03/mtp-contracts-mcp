# MTP 用例 JSON 参考

来源：`mtp-contracts-core/src/mtp_contracts/case_schema.json`（JSON Schema Draft 2020-12）+ 语义校验，
字段名与约束与校验器完全一致。**所有对象都是 `additionalProperties: false`**——
写了 schema 里没有的字段会直接报 `schema` 错误。

## 1. 用例对象（`build_suite` 入参的 `cases[]`）

### 必填

| 字段 | 约束 | 说明 |
| --- | --- | --- |
| `schema_version` | 整数，只能是 `1` | 缺省时服务会补 `1` |
| `id` | `^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$` | 套件内唯一（**允许点**） |
| `title` | 1~200 字符 | |
| `steps` | 数组，至少 1 项 | 元素是步骤对象 |

### 可选

| 字段 | 约束 | 说明 |
| --- | --- | --- |
| `description` | string | |
| `module` | string（非空） | |
| `priority` | `P0` / `P1` / `P2` / `P3` | |
| `tags` | string[]，不重复 | |
| `environment` | 对象，`name` 必填；可含 `base_url`、`db`；允许自定义键 | `db` 必有 `host` + `database`，另可 `port` / `user` / `password`；用 `{{ env.xxx }}` 引用 |
| `secrets` | 对象，值是非空字符串 | 值就是测试凭证，用 `{{ secrets.xxx }}` 引用；结果与证据会脱敏 |
| `variables` | 对象（任意结构） | 用 `{{ vars.xxx }}` 引用 |
| `timeout_sec` | 数字 > 0 | |
| `retry` | 整数 0~5 | |
| `on_failure` | `abort`（默认）/ `continue` | 步骤失败后是否继续 |
| `fixtures` | fixture 数组 | 数据准备，最早执行、清理必执行 |
| `preconditions` | 步骤数组 | |
| `assertions` | 断言数组 | 在 `steps` 之后执行 |
| `postconditions` | 步骤数组 | 清理，成功/失败/取消都会执行 |

## 2. 步骤对象（`steps` / `preconditions` / `postconditions`）

必填：`id`（`^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`，**不允许点**）、`action`（`^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$`）

| 可选字段 | 约束 | 说明 |
| --- | --- | --- |
| `description` | string | |
| `args` | 对象 | 具体键由 action 决定 |
| `timeout_sec` | 数字 > 0 | |
| `retry` | 整数 0~5 | |
| `retry_delay_ms` | 整数 0~60000 | |
| `on_failure` | `abort` / `continue` | |
| `evidence` | 数组，取值 `screenshot` / `snapshot` / `console` / `network` / `trace` / `text`，不重复 | 见第 5 节，当前只有 `screenshot` 会真正落盘 |
| `continue_on_error` | bool | 等价于该步 `on_failure: continue` |
| `expect_failure` | bool | 负向用例：该步「本就该失败」，失败→通过、成功→失败 |

fixture 额外字段：`verify`（断言数组，准备完立即校验）、
`cleanup`（对象，`action` 必填，另可 `args` / `timeout_sec` / `required`）。

执行顺序：`fixtures` → `preconditions` → `steps` → `assertions` → `postconditions` → fixture 清理（倒序、必执行）。

## 3. 断言对象

必填：`type`。顶层断言还必须给 `id`（同用例内唯一，`^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$`）。

| 可选字段 | 说明 |
| --- | --- |
| `description` / `message` | `message` 会替换默认失败描述 |
| `actual` / `expected` | 通常写 `{{ ... }}` 表达式；`expected` 也可以写字面量 |
| `source` | 提供上下文句柄的步骤，如 `{{ steps.open-login }}`（`json_path`、`page_text_contains`、`element_visible` 用） |
| `args` | 各类型自己的参数，见下表 |
| `items` | `all` / `any` 的子断言数组（至少 1 项） |
| `severity` | `blocker` / `critical` / `major`（默认）/ `minor` |

### 各类型怎么用

| type | 必需 | 说明 |
| --- | --- | --- |
| `equals` | `actual` + `expected` | 数字按数值比、字符串按文本比；布尔不放宽（`True` ≠ `"true"`） |
| `contains` | `actual` + `expected` | `actual` 是数组→任一元素相等；是字符串→子串包含 |
| `status_code` | `actual` + `expected` | `actual` 可直接指某个 http 步骤结果，自动取 `http_status` |
| `json_path` | `source` + `args.path`（可选 `args.expected`） | 用 JSONPath 取多值；给了 `expected` 就比对，否则只要求「有匹配」 |
| `json_schema` | `source` + `args.schema` 或 `args.schema_file` | 用 jsonschema 校验结构 |
| `response_time` | `actual` + `expected`，可选 `args.mode`（`lte` 默认 / `lt` / `gte` / `gt` / `eq`） | 单位毫秒 |
| `page_text_contains` | `expected`（或 `args.text`） | 页面文本包含；不给 `source` 时自动取一次页面快照 |
| `element_visible` | `args.target`（CSS 选择器），可选 `args.timeout_ms` | 通过浏览器现场查询可见性（display / visibility / opacity / 尺寸） |
| `file_exists` | `args.path`，可选 `args.min_bytes` | 判断本地文件存在与大小 |
| `exit_code` | `actual` + `expected` | 取命令的退出码 |
| `db_value` | `actual` + `expected`，可选 `args.column` / `args.row`（默认第 0 行） | **`actual` 指向 `mysql.query` 步骤时最有用**：`args.column` + `args.row` 可精确取某一列某一行 |
| `all` / `any` | `items` | 递归组合子断言 |

`db_value` 按行取值的写法（同一列断言多行时用它，不必把 SQL 拆成多条）：

```json
{"id": "a-cfgbypass-235", "type": "db_value", "description": "10.235 CfgByPass 应为 0",
 "actual": "{{ steps.db-query-bypass }}", "args": {"column": "CfgByPass", "row": 0}, "expected": "0"},
{"id": "a-cfgbypass-41", "type": "db_value", "description": "10.41 CfgByPass 应为 0",
 "actual": "{{ steps.db-query-bypass }}", "args": {"column": "CfgByPass", "row": 1}, "expected": "0"}
```

行号越界会直接判失败（消息形如「结果集只有 1 行，取不到第 1 行」），
所以「结果里本该有两台设备、实际只有一台」这种问题会被断言抓住。

## 4. 内置 action 清单

动作、参数、返回字段的**唯一事实来源**是 core 的 `mtp_contracts.action_catalog`：
MCP 的 `build_suite` 与平台上传校验都读它，MCP 服务说明也是由它生成，所以这里不再手抄一份（手抄会漂移）。

```bash
uv run --without mtp-contracts-mcp --with mtp-contracts-core==0.1.2 \
  python -c "from mtp_contracts.action_catalog import render_text; print(render_text())"
```

`action` 的命名空间就是适配器名：`playwright.*`（浏览器）、`api.*`（直连 HTTP，不经浏览器）、
`mysql.*`、`ssh.*`。只收录**已实现**的动作，未收录的一律按未知 action 报错。

几条容易踩的写法（目录里有，但值得单独说）：

- `playwright.click` / `type` / `hover` / `wait_for`：`args.target` 是 **CSS 或 Playwright selector**，
  例如 `button:has-text('跳过')`、`.el-table__body tr:has-text('192.168.10.235') .el-checkbox`、`text=处理完成`。
- `click` 的返回值是 `clicked <选择器>`，**不是页面正文**；要断言页面内容必须另外 `wait_for` + `snapshot`，
  再断言 `page_text`。`wait_for` 用 `text=xxx` 等**明确信号**，不要用 `time` 代替结果等待。
- `mysql.query` 必须带 `args.credentials`（如 `"{{ env.db }}"`），结果在 `steps.<id>.rows`，
  所以列引用形如 `{{ steps.db-query.rows[0].CfgByPass }}`。
- `ssh.execute`：`args.host` / `user` / `password`（`{{ secrets.xxx }}`）+ `args.command`。
  断言请针对 `stdout` / `exit_code`，**不要**拿整个步骤对象做包含判断——它含原始 command。

## 5. 变量引用与证据约定

可用命名空间（引用必须已声明，否则语义校验报错）：

```
{{ env.<key> }}            environment 里的键
{{ vars.<name> }}          variables 或 secrets 里的键
{{ secrets.<name> }}       secrets 里的键（值会被脱敏）
{{ steps.<step-id>.<字段> }} 引用前面步骤的产出，如 {{ steps.verify-push-result.page_text }}
{{ run.id }}  {{ run.case_id }}  {{ now.iso }}  {{ now.epoch }}
```

`secrets` 块里的「值」就是**实际凭证**（`{逻辑名: 真实值}`），不是环境变量名，也不是引用；校验器不解析这一块。含真实凭证的套件不要提交到 Git。

**截图证据（mtp-platform 当前策略）**：

- 只在**宏观重要步骤**的收尾处声明 `"evidence": ["screenshot"]`，一次声明 = 一张整页 PNG；
  打开浏览器、点导航这类技术步骤不要声明。
- 声明 `snapshot` / `console` / `network` / `text` 目前也只会得到一张截图。
- 浏览器步骤**失败**时平台自动补一张截图，无需声明。
- `mysql` / `ssh` / `api` 这类截不了图的步骤不采集证据；它们的输出在用例详情的「步骤输出」里可见。

## 6. 可直接复制的示例

最小可用用例：

```json
{
  "cases": [
    {
      "schema_version": 1,
      "id": "login-success",
      "title": "正常登录",
      "steps": [
        {"id": "open", "action": "playwright.navigate", "args": {"url": "https://example.test/login"}}
      ]
    }
  ]
}
```

带环境、凭证、多类步骤与断言的用例：

```json
{
  "cases": [
    {
      "schema_version": 1,
      "id": "TC-bypass-disable-verify",
      "title": "网关 bypass 关闭态验证（Web + MySQL + SSH）",
      "module": "gateway",
      "priority": "P1",
      "tags": ["bypass", "regression"],
      "environment": {
        "name": "lab",
        "web_url": "http://192.168.101.57:19999/",
        "db": {"host": "192.168.10.19", "port": 3306, "database": "gateway", "user": "reader"}
      },
      "secrets": {"ssh_password": "替换为真实测试凭证", "db_password": "替换为真实测试凭证"},
      "variables": {"devices": ["192.168.10.235", "192.168.10.41"]},
      "steps": [
        {"id": "open-web", "action": "playwright.navigate", "args": {"url": "{{ env.web_url }}"}},
        {"id": "skip-ukey", "action": "playwright.click", "args": {"target": "button:has-text('跳过')"}},
        {"id": "query", "action": "playwright.click", "args": {"target": "button:has-text('查询')"}},
        {"id": "pick-235", "action": "playwright.click",
         "args": {"target": ".el-table__body tr:has-text('192.168.10.235') .el-checkbox"}},
        {"id": "pick-41", "action": "playwright.click",
         "args": {"target": ".el-table__body tr:has-text('192.168.10.41') .el-checkbox"}},
        {"id": "push", "action": "playwright.click", "args": {"target": "button:has-text('下发配置')"}},
        {"id": "wait-done", "action": "playwright.wait_for", "args": {"target": "text=处理完成", "timeout": 30000}},
        {"id": "verify-page", "action": "playwright.snapshot", "args": {},
         "evidence": ["screenshot"]},
        {"id": "db-check", "action": "mysql.query",
         "args": {"credentials": "{{ env.db }}",
                  "sql": "SELECT deviceip, CfgByPass FROM deviceinfo WHERE deviceip IN ('192.168.10.235','192.168.10.41') ORDER BY deviceip;"}},
        {"id": "ssh-state", "action": "ssh.execute",
         "args": {"host": "192.168.11.231", "user": "root", "password": "{{ secrets.ssh_password }}",
                  "command": "cat /tmp/bypass | head -20", "timeout": 60}}
      ],
      "assertions": [
        {"id": "a-push-ok", "type": "page_text_contains", "description": "下发结果应成功 2 台",
         "source": "{{ steps.verify-page }}", "expected": "成功 2", "severity": "critical"},
        {"id": "a-235", "type": "db_value", "description": "10.235 应为关闭态",
         "actual": "{{ steps.db-check }}", "args": {"column": "CfgByPass", "row": 0}, "expected": "0"},
        {"id": "a-41", "type": "db_value", "description": "10.41 应为关闭态",
         "actual": "{{ steps.db-check }}", "args": {"column": "CfgByPass", "row": 1}, "expected": "0"},
        {"id": "a-ssh", "type": "contains", "description": "通道状态应含 NORMAL",
         "actual": "{{ steps.ssh-state.stdout }}", "expected": "NORMAL"}
      ]
    }
  ]
}
```

提交前务必先跑一次 `build_suite`（见 `SKILL.md`），确认 `ok: true`。
