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
