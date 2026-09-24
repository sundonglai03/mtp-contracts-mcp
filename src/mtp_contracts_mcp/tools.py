"""Build one deterministic JSON suite from candidate case objects."""

from __future__ import annotations

from typing import Any

from mtp_contracts.case_validator import SUPPORTED_SCHEMA_VERSIONS, lint_suite, validate_case


def _issue(
    *,
    case_index: int | None,
    case_id: str | None,
    path: str,
    code: str,
    message: str,
) -> dict[str, int | str | None]:
    """固定的问题形状：`errors`（阻断）与 `warnings`（不阻断的忠告）共用。"""
    return {
        "case_index": case_index,
        "case_id": case_id,
        "path": path,
        "code": code,
        "message": message,
    }


def _failure(
    errors: list[dict[str, int | str | None]],
    warnings: list[dict[str, int | str | None]] | None = None,
) -> dict[str, Any]:
    return {"ok": False, "suite": None, "errors": errors, "warnings": warnings or []}


def build_suite(cases: Any = None) -> dict[str, Any]:
    """Validate case JSON objects and return one JSON suite, never a partial result.

    `warnings` 不阻断生成：它们是「契约合法、但很可能在平台上跑不稳 / 跑不过」的
    运行期忠告（缺 navigate、固定睡眠、没有断言、没有证据、整对象断言），
    写用例的 agent 按它自查即可，不必去读平台文档。
    """
    if cases is None:
        return _failure(
            [
                _issue(
                    case_index=None,
                    case_id=None,
                    path="cases",
                    code="required",
                    message="cases 必填且不能为空",
                )
            ]
        )
    if not isinstance(cases, list):
        return _failure(
            [
                _issue(
                    case_index=None,
                    case_id=None,
                    path="cases",
                    code="invalid_cases_type",
                    message="cases 必须是 JSON 数组",
                )
            ]
        )
    if not cases:
        return _failure(
            [
                _issue(
                    case_index=None,
                    case_id=None,
                    path="cases",
                    code="empty_cases",
                    message="cases 必填且不能为空",
                )
            ]
        )

    errors: list[dict[str, int | str | None]] = []
    warnings: list[dict[str, int | str | None]] = []
    normalized_cases: list[dict[str, Any]] = []
    seen_ids: dict[str, int] = {}

    for index, candidate in enumerate(cases):
        if not isinstance(candidate, dict):
            errors.append(
                _issue(
                    case_index=index,
                    case_id=None,
                    path="",
                    code="invalid_case_type",
                    message="用例必须是 JSON 对象",
                )
            )
            continue

        # Do not infer or rewrite business steps. This is the only normalization.
        case = dict(candidate)
        case.setdefault("schema_version", SUPPORTED_SCHEMA_VERSIONS[-1])
        case_id = case.get("id") if isinstance(case.get("id"), str) else None

        result = validate_case(case)
        for issue in result.issues:
            errors.append(
                _issue(
                    case_index=index,
                    case_id=case_id,
                    path=issue.path,
                    # 用问题码（unknown_action / missing_arg / invalid_arg_type …）；
                    # 没有专门码时沿用 kind（schema / semantics）。
                    code=issue.error_code,
                    message=issue.message,
                )
            )
        for issue in result.warnings:
            warnings.append(
                _issue(
                    case_index=index,
                    case_id=case_id,
                    path=issue.path,
                    code=issue.error_code,
                    message=issue.message,
                )
            )

        if case_id is not None:
            if case_id in seen_ids:
                errors.append(
                    _issue(
                        case_index=index,
                        case_id=case_id,
                        path="id",
                        code="duplicate_id",
                        message=f"用例 id 与 cases[{seen_ids[case_id]}] 重复",
                    )
                )
            else:
                seen_ids[case_id] = index
        normalized_cases.append(case)

    # 套件级忠告：一个功能点应该是一条用例（同一流程的多个阶段要写成同一条用例的多个步骤）。
    # 逐用例的 lint 看不到「这 10 条其实是一条流程」，只有把整个 cases 放一起才看得出来。
    for issue in lint_suite(normalized_cases):
        warnings.append(
            _issue(
                case_index=None,
                case_id=None,
                path=issue.path,
                code=issue.error_code,
                message=issue.message,
            )
        )

    if errors:
        return _failure(errors, warnings)
    return {
        "ok": True,
        "suite": {"cases": normalized_cases},
        "errors": [],
        "warnings": warnings,
    }
