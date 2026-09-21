#!/usr/bin/env python3
"""调用 mtp-contracts-mcp 的 build_suite 校验 MTP 用例。

用法：
    uv run --quiet --with "mcp>=2.0" build_suite.py cases.json
    uv run --quiet --with "mcp>=2.0" build_suite.py cases.json --out suite.json
    uv run --quiet --with "mcp>=2.0" build_suite.py cases.json --url http://192.168.11.231:8000/mcp
    MTP_CONTRACTS_MCP_TOKEN=xxx uv run --quiet --with "mcp>=2.0" build_suite.py cases.json

入参文件可以是 {"cases": [...]}，也可以是裸的用例数组。
退出码：0 = ok:true（套件已写出）；1 = 校验失败（errors 已打印）；2 = 调用本身出错。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from typing import Any

DEFAULT_URL = "http://192.168.11.231:8000/mcp"
DEFAULT_TIMEOUT = 20.0


def load_cases(path: str) -> list[dict[str, Any]]:
    with open(path, encoding="utf-8") as fh:
        payload = json.load(fh)
    if isinstance(payload, dict) and "cases" in payload:
        payload = payload["cases"]
    if not isinstance(payload, list) or not payload:
        raise SystemExit(f'{path}: 需要非空数组，或 {{"cases": [...]}}')
    return payload


def describe_error(exc: BaseException) -> str:
    """把 ExceptionGroup 里的真实原因摊平。

    MCP 客户端跑在 anyio TaskGroup 里，异常会被包成 ExceptionGroup；直接打印
    只能看到「unhandled errors in a TaskGroup」，等于没有信息。这里递归下钻，
    把最内层异常的类型和消息拼出来。
    """
    parts: list[str] = []

    def walk(err: BaseException) -> None:
        children = getattr(err, "exceptions", None)
        if children:
            for child in children:
                walk(child)
            return
        parts.append(f"{type(err).__name__}: {err}")

    walk(exc)
    return " | ".join(dict.fromkeys(parts)) or type(exc).__name__


def make_http_client(headers: dict[str, str], *, use_env_proxy: bool):
    """构造 MCP 用的 httpx 客户端。

    - 默认直连（`trust_env=False`）：内网 MCP 走本地网络，同时避免本机配了 socks
      代理却缺 `socksio` 时连客户端都建不起来；
    - `use_env_proxy=True`：改用环境里的代理（有些机器必须经代理才能到 MCP）。
      若确实是 socks 代理但没装 socksio，就只丢掉 socks 那条，保留 http/https 代理；
    - 拿不到 httpx2 时退化为清空代理环境变量，返回 None 由 SDK 自己建客户端。
    """
    try:
        import httpx2
    except ImportError:  # pragma: no cover - 极端环境
        for name in (
            "ALL_PROXY",
            "all_proxy",
            "HTTP_PROXY",
            "http_proxy",
            "HTTPS_PROXY",
            "https_proxy",
        ):
            os.environ.pop(name, None)
        return None

    if not use_env_proxy:
        return httpx2.AsyncClient(trust_env=False, headers=headers, timeout=DEFAULT_TIMEOUT)

    try:
        return httpx2.AsyncClient(trust_env=True, headers=headers, timeout=DEFAULT_TIMEOUT)
    except ImportError:
        for name in ("ALL_PROXY", "all_proxy"):
            os.environ.pop(name, None)
        return httpx2.AsyncClient(trust_env=True, headers=headers, timeout=DEFAULT_TIMEOUT)


async def call_build_suite(url: str, cases: list[dict[str, Any]], http_client: Any) -> dict[str, Any]:
    """一次完整的 MCP 调用；结束时（成功或失败）都在同一事件循环里关掉客户端。"""
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    try:
        async with streamable_http_client(url, http_client=http_client) as streams:
            # mcp 2.x 返回二元组，早期版本是三元组（多一个 session id 回调）
            read, write = streams[0], streams[1]
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool("build_suite", {"cases": cases})
    finally:
        if http_client is not None and hasattr(http_client, "aclose"):
            try:
                await http_client.aclose()
            except Exception:  # noqa: BLE001 - 关闭失败不影响结果
                pass

    payload = getattr(result, "structured_content", None) or getattr(
        result, "structuredContent", None
    )
    if payload is None:
        for item in getattr(result, "content", None) or []:
            text = getattr(item, "text", None)
            if text:
                payload = json.loads(text)
                break
    if not isinstance(payload, dict):
        raise RuntimeError("服务返回里没有可解析的 JSON 结果")
    return payload


def validate_remote(url: str, cases: list[dict[str, Any]], token: str | None) -> dict[str, Any]:
    """先直连，失败再用环境代理重试一次；两种都失败就把真实原因抛出去。"""
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    last: BaseException | None = None
    for use_env_proxy in (False, True):
        client = make_http_client(headers, use_env_proxy=use_env_proxy)
        try:
            return asyncio.run(call_build_suite(url, cases, client))
        except BaseException as exc:  # noqa: BLE001 - 逐个策略重试
            last = exc
    assert last is not None
    raise last


def main() -> int:
    parser = argparse.ArgumentParser(description="用 mtp-contracts-mcp 校验 MTP 用例")
    parser.add_argument("cases_file", help='用例文件：{"cases": [...]} 或裸数组')
    parser.add_argument("--url", default=os.environ.get("MTP_CONTRACTS_MCP_URL", DEFAULT_URL))
    parser.add_argument("--token", default=os.environ.get("MTP_CONTRACTS_MCP_TOKEN") or None)
    parser.add_argument("--out", default="suite.json", help="校验通过时写出的套件（默认 suite.json）")
    args = parser.parse_args()

    cases = load_cases(args.cases_file)
    try:
        payload = validate_remote(args.url, cases, args.token)
    except BaseException as exc:  # noqa: BLE001 - 命令行工具，给出可操作的提示
        print(f"调用失败: {describe_error(exc)}", file=sys.stderr)
        print(f"  端点: {args.url}（直连与环境代理都试过）", file=sys.stderr)
        print("  请检查：网络 / VPN 是否可达该主机、端点地址与端口、是否需要 Token", file=sys.stderr)
        return 2

    if payload.get("ok"):
        suite = payload.get("suite") or {}
        with open(args.out, "w", encoding="utf-8") as fh:
            json.dump(suite, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        print(f"ok: true，{len(suite.get('cases') or [])} 个用例已写入 {args.out}")
        return 0

    errors = payload.get("errors") or []
    print(f"ok: false，{len(errors)} 个问题：")
    for item in errors:
        where = item.get("case_id") or f"cases[{item.get('case_index')}]"
        print(
            f"  - [{item.get('code')}] {where} "
            f"{item.get('path') or '(root)'}: {item.get('message')}"
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
