"""Build one deterministic JSON suite from candidate case objects."""

from __future__ import annotations

from typing import Any

from mtp_contracts.case_validator import SUPPORTED_SCHEMA_VERSIONS, validate_case

def _error(
    *,
    case_index: int | None,
    case_id: str | None,
    path: str,
    code: str,
    message: str,
) -> dict[str, int | str | None]:
    """Return the fixed error shape exposed by this service."""
    return {
        "case_index": case_index,
        "case_id": case_id,
        "path": path,
        "code": code,
        "message": message,
    }


def _failure(errors: list[dict[str, int | str | None]]) -> dict[str, Any]:
    return {"ok": False, "suite": None, "errors": errors}


def build_suite(cases: Any = None) -> dict[str, Any]:
    """Validate case JSON objects and return one JSON suite, never a partial result."""
    if cases is None:
        return _failure(
            [_error(case_index=None, case_id=None, path="cases", code="required", message="cases 必填且不能为空")]
        )
    if not isinstance(cases, list):
        return _failure(
            [_error(case_index=None, case_id=None, path="cases", code="invalid_cases_type", message="cases 必须是 JSON 数组")]
        )
    if not cases:
        return _failure(
            [_error(case_index=None, case_id=None, path="cases", code="empty_cases", message="cases 必填且不能为空")]
        )

    errors: list[dict[str, int | str | None]] = []
    normalized_cases: list[dict[str, Any]] = []
    seen_ids: dict[str, int] = {}

    for index, candidate in enumerate(cases):
        if not isinstance(candidate, dict):
            errors.append(
                _error(
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

        for issue in validate_case(case).issues:
            errors.append(
                _error(
                    case_index=index,
                    case_id=case_id,
                    path=issue.path,
                    code=issue.kind,
                    message=issue.message,
                )
            )

        if case_id is not None:
            if case_id in seen_ids:
                errors.append(
                    _error(
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

    if errors:
        return _failure(errors)
    return {"ok": True, "suite": {"cases": normalized_cases}, "errors": []}
