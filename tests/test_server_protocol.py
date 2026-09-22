"""Protocol tests for the Streamable HTTP MCP service."""

from __future__ import annotations

import json

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


async def test_protocol_exposes_one_tool_and_always_returns_json_result_shape():
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client_for(app) as client:
            async with streamable_http_client(
                "http://127.0.0.1:8000/mcp", http_client=client, terminate_on_close=False
            ) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    assert {tool.name for tool in listed.tools} == {"build_suite"}
                    assert listed.tools[0].input_schema["required"] == ["cases"]
                    assert listed.tools[0].input_schema["properties"]["cases"] == {
                        "description": "必填的非空 JSON 数组；每项必须是一个测试用例 JSON 对象",
                        "type": "array",
                        "minItems": 1,
                        "items": {"type": "object"},
                    }

                    success = await session.call_tool(
                        "build_suite",
                        {
                            "cases": [
                                {
                                    "id": "P-1",
                                    "title": "protocol case",
                                    "steps": [{"id": "s1", "action": "playwright.snapshot"}],
                                }
                            ]
                        },
                    )
                    failure = await session.call_tool("build_suite", {"cases": ["not an object"]})

    for result, expected_ok in ((success, True), (failure, False)):
        assert not result.is_error
        assert len(result.content) == 1
        payload = json.loads(result.content[0].text)
        assert set(payload) == {"ok", "suite", "errors", "warnings"}
        assert payload["ok"] is expected_ok
    assert success.structured_content["suite"]["cases"][0]["schema_version"] == 1
    assert failure.structured_content["errors"][0]["code"] == "invalid_case_type"


async def test_mcp_bearer_token_is_optional(monkeypatch):
    monkeypatch.setenv("MTP_CONTRACTS_MCP_TOKEN", "test-token")
    app = create_app()
    async with app.router.lifespan_context(app):
        async with _client_for(app) as client:
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

    assert denied.status_code == 401
    assert allowed.status_code != 401
