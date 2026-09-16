"""mtp-contracts-mcp 服务端：把 contracts-core 暴露为 Streamable HTTP MCP 服务。

只提供确定性工具：校验、规范化、schema、错误解释。不执行测试、不连目标系统。

基于 **mcp 2.x**（`mcp.server.mcpserver.MCPServer`）。注意与 1.x 的差异：
- 1.x 的 `FastMCP` 在 2.x 改名为 `MCPServer`；
- `host/port/json_response/stateless_http` 等不再在构造器里，而是 `streamable_http_app()` / `run()` 的参数；
- 自定义 HTTP 路由用 `@server.custom_route(...)`（免鉴权，适合 healthcheck）。
"""

from __future__ import annotations

import argparse
import functools
import hmac
import os
from typing import Annotated, Any

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse

from mtp_contracts_mcp import tools

DEFAULT_HOST = os.environ.get("MTP_CONTRACTS_MCP_HOST", "127.0.0.1")
DEFAULT_PORT = int(os.environ.get("MTP_CONTRACTS_MCP_PORT", "8000"))
STREAMABLE_HTTP_PATH = "/mcp"

# Host 白名单（DNS rebinding 防护）。SDK 默认只放行本机，容器/内网访问会被拒。
# 用 MTP_CONTRACTS_MCP_ALLOWED_HOSTS 覆盖（逗号分隔，支持 "host:*"）；设为 off 关闭校验。
DEFAULT_ALLOWED_HOSTS = ["127.0.0.1:*", "localhost:*", "[::1]:*"]


class McpBearerAuthMiddleware:
    """可选的 MCP Bearer Token；health 保持公开供容器探活。"""

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
    "测试用例规范服务：把不同来源的用例校验、规范化为统一格式。"
    "只做确定性处理，不执行测试、不连接 SSH/MySQL/浏览器。"
)


def safe_tool(fn):
    """把任意异常转成 ToolError，否则 SDK 会吞掉原因（只回 'Error executing tool'）。"""

    @functools.wraps(fn)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return fn(*args, **kwargs)
        except ToolError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ToolError(f"{type(exc).__name__}: {exc}") from exc

    return wrapper


def build_mcp() -> MCPServer:
    """每次调用都新建实例（session manager 每实例只能 run 一次）。"""
    server = MCPServer(
        name="mtp-contracts-mcp",
        description="测试用例规范系统",
        instructions=INSTRUCTIONS,
        log_level="INFO",
    )

    @server.tool()
    @safe_tool
    def validate_case(
        case: Annotated[dict | str, Field(description="用例内容：YAML/JSON 文本，或已解析的对象")],
    ) -> dict:
        """校验单个用例，返回是否通过及全部问题（带字段路径）。"""
        return tools.validate_one(case)

    @server.tool()
    @safe_tool
    def validate_suite(
        cases: Annotated[list[dict | str], Field(description="一组用例内容（文本或对象）")],
    ) -> dict:
        """校验一组用例，返回逐条结果与汇总通过率。"""
        return tools.validate_many(cases)

    @server.tool()
    @safe_tool
    def normalize_case(
        case: Annotated[dict | str, Field(description="候选用例内容：YAML/JSON 文本，或已解析的对象")],
    ) -> dict:
        """把候选用例规范化为标准格式，并列出做了哪些补齐（保守、可解释）。"""
        return tools.normalize_one(case)

    @server.tool()
    @safe_tool
    def get_schema() -> dict:
        """返回用例 JSON Schema 与受支持的 schema_version。"""
        return tools.schema_info()

    @server.tool()
    @safe_tool
    def explain_validation_error(
        path: Annotated[str, Field(description="出问题的字段路径，如 steps[0].action")],
        message: Annotated[str, Field(description="校验器给出的原始消息")],
        kind: Annotated[str, Field(description="问题类别：schema / semantics / security")] = "",
    ) -> dict:
        """把校验错误翻译成人能看懂的说明与修复方向。"""
        return tools.explain_error(path, message, kind)

    @server.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        """容器 HEALTHCHECK 用；custom_route 天然免鉴权。"""
        return JSONResponse({"status": "ok", "service": "mtp-contracts-mcp"})

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
