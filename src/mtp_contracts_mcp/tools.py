"""测试用例规范工具（确定性；不调用大模型、不执行测试）。

供 MCP 服务与本地脚本共用，全部构建在内联 contracts-core 之上：
所有校验逻辑来自 `mtp_contracts_mcp.contracts`，不另写一套。
"""

from __future__ import annotations

import json
from typing import Any

import yaml

from mtp_contracts_mcp.contracts.case_validator import (
    SUPPORTED_SCHEMA_VERSIONS,
    load_schema,
    validate_case,
)

_PHASE_LABELS = {
    "fixtures": "夹具",
    "preconditions": "前置条件",
    "steps": "步骤",
    "postconditions": "后置条件",
    "assertions": "断言",
}


class CaseInputError(ValueError):
    """输入的用例无法解析为映射。"""


def parse_case(payload: dict[str, Any] | str) -> dict[str, Any]:
    """把 dict 或 YAML/JSON 文本解析成用例映射。"""
    if isinstance(payload, dict):
        return payload
    if isinstance(payload, str):
        try:
            data = yaml.safe_load(payload)
        except yaml.YAMLError as exc:  # noqa: BLE001
            raise CaseInputError(f"YAML/JSON 解析失败: {exc}") from exc
        if isinstance(data, dict):
            return data
        raise CaseInputError(f"用例根节点必须是映射，实际是 {type(data).__name__}")
    raise CaseInputError(f"不支持的输入类型: {type(payload).__name__}")


def _issues_to_list(result: Any) -> list[dict[str, str]]:
    return [{"path": i.path, "message": i.message, "kind": i.kind} for i in result.issues]


def validate_one(payload: dict[str, Any] | str) -> dict[str, Any]:
    """校验单个用例。"""
    case = parse_case(payload)
    result = validate_case(case)
    return {
        "ok": result.ok,
        "issue_count": len(result.issues),
        "issues": _issues_to_list(result),
        "case_id": case.get("id"),
        "schema_version": case.get("schema_version"),
    }


def validate_many(payloads: list[dict[str, Any] | str]) -> dict[str, Any]:
    """校验一组用例，返回汇总 + 每条结果。"""
    results = []
    failed = 0
    for index, payload in enumerate(payloads):
        try:
            item = validate_one(payload)
        except CaseInputError as exc:
            item = {"ok": False, "issue_count": 1, "issues": [{"path": "", "message": str(exc), "kind": "input"}]}
        item["index"] = index
        results.append(item)
        if not item["ok"]:
            failed += 1
    return {
        "ok": failed == 0,
        "total": len(payloads),
        "passed": len(payloads) - failed,
        "failed": failed,
        "results": results,
    }


def normalize_one(payload: dict[str, Any] | str) -> dict[str, Any]:
    """把候选用例规范化为标准格式（保守：只做确定、可解释的补齐）。"""
    case = parse_case(payload)
    changes: list[str] = []

    # 1) 去掉平台内部键（`_` 前缀）
    cleaned = {k: v for k, v in case.items() if not str(k).startswith("_")}
    if len(cleaned) != len(case):
        changes.append("移除平台内部键（_ 前缀）")

    # 2) 补齐 schema_version
    if "schema_version" not in cleaned:
        cleaned["schema_version"] = SUPPORTED_SCHEMA_VERSIONS[-1]
        changes.append(f"补齐 schema_version={cleaned['schema_version']}")

    # 3) 显式补空列表，避免下游反复判空
    for field in ("fixtures", "preconditions", "steps", "postconditions", "assertions"):
        if field not in cleaned:
            cleaned[field] = []
            changes.append(f"补齐空的 {field}")

    result = validate_case(cleaned)
    return {
        "ok": result.ok,
        "case": cleaned,
        "changes": changes,
        "issues": _issues_to_list(result),
    }


def schema_info() -> dict[str, Any]:
    """返回 JSON Schema 与支持的 schema_version。"""
    return {
        "schema_version_supported": list(SUPPORTED_SCHEMA_VERSIONS),
        "json_schema": load_schema(),
    }


def explain_error(path: str, message: str, kind: str = "") -> dict[str, str]:
    """把校验错误翻译成人能看懂的说明与修复方向。"""
    where = path or "(根)"
    hint = _hint_for(path, message)
    return {
        "path": where,
        "message": message,
        "kind": kind or "schema",
        "plain": f"位置 {where}：{message}",
        "hint": hint,
    }


def _hint_for(path: str, message: str) -> str:
    head = path.split(".", 1)[0]
    phase = path.split("[")[0]
    label = _PHASE_LABELS.get(phase, phase)

    if "缺少必填字段" in message:
        return f"给 {label} 的该条目补上这个必填字段。"
    if "明文凭据" in message or "secrets" in message:
        return "不要把真实密码写进用例；改用 {{ secrets.<逻辑名> }}，真实值经环境变量注入。"
    if "重复" in message:
        return "同一用例内 id 必须唯一，改掉重复的那个。"
    if "不支持的 schema_version" in message:
        return f"改用受支持的 schema_version：{list(SUPPORTED_SCHEMA_VERSIONS)}。"
    if "未知命名空间" in message:
        return "变量引用只支持 env / vars / secrets / steps / run / now 这些命名空间。"
    if "引用了不存在" in message or "未定义" in message:
        return "引用的步骤/变量还没声明；检查拼写或先声明它。"
    if head == "steps" or phase in _PHASE_LABELS:
        return f"检查 {label} 里该条目的字段是否符合 schema（action 形如 adapter.action）。"
    return "对照 get_schema 返回的 JSON Schema 检查该字段。"


def explain_errors(issues: list[dict[str, str]]) -> list[dict[str, str]]:
    return [explain_error(i.get("path", ""), i.get("message", ""), i.get("kind", "")) for i in issues]


def dump_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)
