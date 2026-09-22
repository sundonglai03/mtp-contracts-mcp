"""mtp-contracts-mcp: validate one JSON suite through Streamable HTTP MCP.

只提供一个确定性工具；不执行测试、不连目标系统。

基于 **mcp 2.x**（`mcp.server.mcpserver.MCPServer`）。注意与 1.x 的差异：
- 1.x 的 `FastMCP` 在 2.x 改名为 `MCPServer`；
- `host/port/json_response/stateless_http` 等不再在构造器里，而是 `streamable_http_app()` / `run()` 的参数；
"""

from __future__ import annotations

import argparse
import hmac
import os
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from mtp_contracts.action_catalog import render_text as render_actions
from pydantic import BaseModel, Field
from starlette.applications import Starlette
from starlette.responses import JSONResponse

from mtp_contracts_mcp import tools

DEFAULT_HOST = os.environ.get("MTP_CONTRACTS_MCP_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("MTP_CONTRACTS_MCP_PORT", "8000"))
STREAMABLE_HTTP_PATH = "/mcp"

# Host 白名单（DNS rebinding 防护）。SDK 默认只放行本机，容器/内网访问会被拒。
# 用 MTP_CONTRACTS_MCP_ALLOWED_HOSTS 覆盖（逗号分隔，支持 "host:*"）；设为 off 关闭校验。
DEFAULT_ALLOWED_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]


class McpBearerAuthMiddleware:
    """可选的 MCP Bearer Token。"""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: dict, receive: Any, send: Any) -> None:
        token = os.environ.get("MTP_CONTRACTS_MCP_TOKEN", "")
        path = str(scope.get("path", ""))
        if token and scope.get("type") == "http" and (
            path == STREAMABLE_HTTP_PATH or path.startswith(STREAMABLE_HTTP_PATH + "/")
        ):
            headers = {
                key.decode("latin-1").lower(): value.decode("latin-1")
                for key, value in scope.get("headers", [])
            }
            supplied = headers.get("authorization", "")
            expected = f"Bearer {token}"
            if not hmac.compare_digest(supplied, expected):
                response = JSONResponse(
                    {"error": "unauthorized", "message": "需要有效的 Bearer Token"},
                    status_code=401,
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def transport_security_from_env() -> TransportSecuritySettings:
    raw = os.environ.get("MTP_CONTRACTS_MCP_ALLOWED_HOSTS", "").strip()
    if raw.lower() in {"off", "disabled", "none"}:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    hosts = [h.strip() for h in raw.split(",") if h.strip()] or DEFAULT_ALLOWED_HOSTS
    return TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hosts)


# 最小可用示例。它本身必须通过校验且 lint 零忠告 —— 改这段说明时一并跑测试验证，
# 否则 agent 照抄会直接失败。
MINIMAL_EXAMPLE = """{
  "schema_version": 1,
  "id": "TC_home_page_open",
  "title": "打开首页并校验页面文本",
  "environment": {"name": "demo", "base_url": "https://192.168.0.10"},
  "variables": {"home_text": "系统首页"},
  "steps": [
    {"id": "open-home", "action": "playwright.navigate", "args": {"url": "{{ env.base_url }}/"}},
    {"id": "snap-home", "action": "playwright.snapshot", "args": {}, "evidence": ["screenshot"]}
  ],
  "assertions": [
    {"id": "a-home-text", "type": "page_text_contains", "source": "{{ steps.snap-home }}",
     "expected": "{{ vars.home_text }}", "severity": "critical"}
  ]
}"""


# 「有就点、没有就跳过」的正确写法：JS 永不抛错（失败留给后面的明确等待）。
# 不能用 on_failure: continue 来当"可选"——平台里任何失败步骤都会让用例判失败。
OPTIONAL_STEP_EXAMPLE = """{"id": "skip-gate-if-present", "action": "playwright.evaluate",
 "args": {"allow_js": true, "function": "async () => { const find = () => Array.from(document.querySelectorAll('button')).find(b => (b.innerText || '').trim() === '跳过'); const deadline = Date.now() + 10000; while (Date.now() < deadline) { const b = find(); if (b) { b.click(); return 'clicked'; } await new Promise(r => setTimeout(r, 200)); } return 'not-present'; }"},
 "description": "有门禁就点掉、没有就返回 not-present —— 这一步永不失败"}"""


INSTRUCTIONS = (
    "用例套件校验服务：只接收 JSON 对象中的非空 cases 数组，返回一个 JSON 套件或"
    "固定结构的校验错误。不会读取文件、解析 YAML、执行测试、调用模型或补写业务步骤。"
    "\n\n校验依据 mtp-contracts-core 的**共用动作目录**（生成器、校验器、执行器同一份）："
    "未知 action、缺必填参数、参数类型不符、重复 id、引用不存在的步骤、引用某步骤"
    "不会返回的字段，都会在创建任务之前带路径报出来。"
    "\n\n返回的 `suite` 字段就是可直接上传给 mtp-platform 的测试套件（形状 "
    '{"cases": [...]}）：把 `suite` 的内容原样保存成 .json 文件即可，平台接受同一形状，'
    "也接受把本工具的完整返回原样上传（平台会自动取其中的 suite）。"
    "\n\n凭证：用例 `secrets` 是 `{逻辑名: 实际凭证}`（直接写真实值，**不是环境变量名**），"
    "用 `{{ secrets.xxx }}` 引用；mysql 步骤必须传 `args.credentials`（可写 "
    '`"{{ env.db }}"` 复用 environment.db 对象）。'
    "\n\n可用动作（由 action_catalog 生成，勿手写）：\n"
    f"{render_actions()}"
    "\n\n【运行期铁律（校验管不到，但决定用例在平台上能不能跑过）】\n"
    "1. 每个用例必须自足：平台会在每个用例开始前重建浏览器会话。web 用例要自己 "
    "playwright.navigate 打开页面并处理登录 / 门禁；确实要复用上一个用例的会话时才写 "
    "reuse_session: true。不要假设上一个用例已经登录、或页面已经打开。\n"
    "2. 等待要显式：navigate 返回不代表页面渲染完成（SPA 组件可能晚几百毫秒才出现）。"
    "用自带自动等待的 playwright.click，或在 evaluate 里轮询、没等到就直接抛错；"
    "不要用一次性 evaluate 去查元素，也不要用 wait_for 的 time 做固定睡眠。\n"
    "3. 参数红线：playwright.evaluate 必须 allow_js: true；mysql.* 必须传 credentials"
    "（可写 \"{{ env.db }}\" 复用 environment.db）；ssh.execute 需要 password 或 ssh_key_filepath。\n"
    "4. 每个用例至少要有断言与证据：浏览器步骤声明 evidence: [\"screenshot\"]；"
    "断言取具体字段（如 {{ steps.x.stdout }}），不要拿整个步骤对象去比较。\n"
    "5. 环境信息（被测地址 / 账号 / 凭证）由使用者提供，写进 environment / variables / secrets，"
    "不要编造目标地址；secrets 写真实值，套件文件本身含凭证，不要提交到 Git。\n"
    "\n【用例结构】必需 schema_version(=1) / id / title / steps。可选：description、module、"
    "priority(P0~P3)、tags、environment(至少含 name，常用 base_url/db)、variables、secrets、"
    "timeout_sec、retry、on_failure(abort|continue)、fixtures、preconditions、postconditions、"
    "reuse_session。\n"
    "步骤：必需 id + action；可选 args、description、timeout_sec（默认 30s）、retry、"
    "retry_delay_ms、on_failure、continue_on_error、expect_failure（负向用例：该步本应失败）、"
    "evidence（声明后会落一张截图）。\n"
    "断言：必需 type；顶层断言还需 id；可选 description、message、severity(blocker|critical|major|minor)。\n"
    "\n【变量引用】只有一种写法 {{ 命名空间.路径 }}：env.* / vars.* / secrets.* / "
    "steps.<step_id>.<字段>（字段必须是该动作「返回」列里的字段）/ run.id / run.case_id / "
    "now.iso / now.epoch；支持下标，如 {{ steps.seed.rows[0].id }}。\n"
    "整个字符串就是一个引用时保留原始类型，所以 credentials 可以写 \"{{ env.db }}\" 把整个对象传进去。\n"
    "\n【断言类型 -> 必填字段】\n"
    "equals / contains / exit_code：actual + expected\n"
    "status_code：actual（如 {{ steps.x.http_status }}）+ expected\n"
    "response_time：actual + expected（毫秒；可用 args.mode 选比较方式）\n"
    "json_path：source={{ steps.x }} + args.path（JSONPath）\n"
    "json_schema：source + args.schema（或 args.schema_file）\n"
    "page_text_contains：source={{ steps.snap }} + expected（页面可见文本）\n"
    "element_visible：source={{ steps.x }} + args.target（Playwright 选择器），可选 args.timeout_ms\n"
    "db_value：actual={{ steps.q.rows[0].列名 }} + expected；可选 args.row / args.column\n"
    "file_exists：args.path；可选 args.min_bytes\n"
    "all / any：items（子断言数组）\n"
    "\n【errors 与 warnings 分别怎么办】\n"
    "errors = 套件**不合法**：必须按每一项的 path/code 改完，改完才可能生成套件。\n"
    "warnings = 套件合法、平台也会接受，但**很可能跑不过**（就是下面铁律对应的坑：没自己"
    "打开页面、固定睡眠、没有断言或证据、断言取整个步骤对象）。它不阻断生成，但你应当先改"
    "掉再交付：它比「能生成」更接近「能跑过」。\n"
    "\n【最小可用示例（可直接照抄改；这份示例本身通过校验且零 warnings）】\n"
    + MINIMAL_EXAMPLE
    + "\n【没有「可选步骤」这回事（最容易写错的一点）】\n"
    "平台里**任何失败步骤都会让用例判失败**：on_failure / continue_on_error 只决定"
    "「失败后要不要继续跑后面的步骤」，并不容忍失败；expect_failure 是给「本应失败的负向"
    "用例」用的（失败才算通过）。所以「有就点、没有就跳过」这类可选交互，必须用一个"
    "**永不抛错**的 evaluate 步骤实现，例如环境有 UKey 门禁时：\n"
    + OPTIONAL_STEP_EXAMPLE
    + "\n（要点：只用 JS 点、找不到就返回状态字符串、绝不 throw；后面另起一步 wait_for 等"
    "「已进首页」的明确信号，把真正的失败暴露在那一层。）\n"
    + "\n\n【交付】把返回的 suite 原样存成 .json 交给测试人员上传到 mtp-platform；"
    "平台接受 {\"cases\": [...]}，也接受本工具的完整返回（会自动取其中的 suite）。"
)


class SuiteError(BaseModel):
    case_index: int | None
    case_id: str | None
    path: str
    code: str
    message: str


class Suite(BaseModel):
    cases: list[dict[str, Any]]


class SuiteResult(BaseModel):
    ok: bool
    suite: Suite | None
    errors: list[SuiteError]
    # 不阻断的运行期忠告：契约合法，但很可能在平台上跑不稳 / 跑不过。
    warnings: list[SuiteError] = []


def build_mcp() -> MCPServer:
    """每次调用都新建实例（session manager 每实例只能 run 一次）。"""
    server = MCPServer(
        name="mtp-contracts-mcp",
        description="测试用例规范系统",
        instructions=INSTRUCTIONS,
        log_level="INFO",
    )

    def build_suite(
        cases: Annotated[
            Any,
            Field(description="必填的非空 JSON 数组；每项必须是一个测试用例 JSON 对象"),
        ] = None,
    ) -> SuiteResult:
        """校验多个 JSON 用例，成功时返回一个 JSON 套件；失败时返回固定 errors 数组。

        按共用动作目录校验动作与参数；errors 里每项的 code 是问题码
        （unknown_action / missing_arg / invalid_arg_type / unknown_result_field …）。
        """
        return SuiteResult.model_validate(tools.build_suite(cases))

    server.add_tool(build_suite)
    registered_tool = server._tool_manager.get_tool("build_suite")
    assert registered_tool is not None
    # The body deliberately accepts raw values so validation failures can use the
    # same result shape. The published schema remains the strict caller contract.
    registered_tool.parameters["properties"]["cases"] = {
        "description": "必填的非空 JSON 数组；每项必须是一个测试用例 JSON 对象",
        "type": "array",
        "minItems": 1,
        "items": {"type": "object"},
    }
    registered_tool.parameters["required"] = ["cases"]

    return server


def create_app(host: str = DEFAULT_HOST) -> Starlette:
    app = build_mcp().streamable_http_app(
        streamable_http_path=STREAMABLE_HTTP_PATH,
        json_response=True,
        stateless_http=True,
        host=host,
        transport_security=transport_security_from_env(),
    )
    app.add_middleware(McpBearerAuthMiddleware)
    return app


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mtp-contracts-mcp", description="测试用例规范系统")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    import uvicorn

    uvicorn.run(create_app(args.host), host=args.host, port=args.port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
