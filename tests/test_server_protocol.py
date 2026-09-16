"""协议级自测：进程内跑完整 MCP 协议（initialize → tools/list → tools/call）。

用 ASGI 直连（`httpx2.ASGITransport`），不需要网络（内网/沙箱可用）。

mcp 2.x 注意点：
- 客户端是 `streamable_http_client(url, http_client=...)`（1.x 是 factory）；
- 只 yield 二元组 `(read, write)`（1.x 是三元组）；
- HTTP 客户端是 `httpx2`，不是 `httpx`。
"""

from __future__ import annotations

import httpx2
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from mtp_contracts_mcp.server import create_app

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend():
    return "asyncio"


def _client_for(app) -> httpx2.AsyncClient:
    return httpx2.AsyncClient(
        transport=httpx2.ASGITransport(app=app), base_url="http://127.0.0.1:8000"
    )


async def test_protocol_lists_and_calls_tools():
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client_for(app) as client:
            async with streamable_http_client(
                "http://127.0.0.1:8000/mcp", http_client=client, terminate_on_close=False
            ) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()

                    listed = await session.list_tools()
                    names = {t.name for t in listed.tools}
                    expected = {
                        "validate_case",
                        "validate_suite",
                        "normalize_case",
                        "get_schema",
                        "explain_validation_error",
                    }
                    assert expected <= names, names

                    result = await session.call_tool("get_schema", {})
                    assert "schema_version_supported" in result.content[0].text


async def test_health_endpoint_is_public():
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client_for(app) as client:
            resp = await client.get("/health")
            assert resp.status_code == 200
            assert resp.json()["status"] == "ok"


async def test_mcp_bearer_token_is_optional_and_health_stays_public(monkeypatch):
    monkeypatch.setenv("MTP_CONTRACTS_MCP_TOKEN", "test-token")
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client_for(app) as client:
            health = await client.get("/health")
            denied = await client.post(
                "/mcp",
                headers={"accept": "application/json", "content-type": "application/json"},
                json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            )
            allowed = await client.post(
                "/mcp",
                headers={
                    "accept": "application/json",
                    "content-type": "application/json",
                    "authorization": "Bearer test-token",
                },
                json={"jsonrpc": "2.0", "id": 1, "method": "ping"},
            )

    assert health.status_code == 200
    assert denied.status_code == 401
    assert allowed.status_code != 401
