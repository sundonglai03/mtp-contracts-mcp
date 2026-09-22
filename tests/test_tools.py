"""Tests for the single JSON suite-building operation."""

from __future__ import annotations

from mtp_contracts_mcp import tools


def _case(case_id: str) -> dict:
    """一个「写对了」的用例：自己开页面、有证据、有断言 —— 不该产生任何 warnings。"""
    return {
        "id": case_id,
        "title": f"case {case_id}",
        "steps": [
            {
                "id": "s1",
                "action": "playwright.navigate",
                "args": {"url": "https://example.local/", "timeout": 5000},
            },
            {
                "id": "s2",
                "action": "playwright.snapshot",
                "args": {},
                "evidence": ["screenshot"],
            },
        ],
        "assertions": [
            {"id": "a1", "type": "page_text_contains", "source": "{{ steps.s2 }}", "expected": "ok"}
        ],
    }


def _assert_error_shape(result: dict) -> None:
    assert set(result) == {"ok", "suite", "errors", "warnings"}
    assert result["ok"] is False
    assert result["suite"] is None
    assert result["errors"]
    assert set(result["errors"][0]) == {
        "case_index",
        "case_id",
        "path",
        "code",
        "message",
    }


def test_build_suite_returns_one_json_suite_and_only_adds_schema_version():
    original = _case("A-1") | {"_source": "/not/a/file"}
    result = tools.build_suite([original, _case("A-2")])

    assert result == {
        "ok": True,
        "suite": {
            "cases": [
                original | {"schema_version": 1},
                _case("A-2") | {"schema_version": 1},
            ]
        },
        "errors": [],
        "warnings": [],
    }
    assert "schema_version" not in original


def test_build_suite_returns_structured_result_for_missing_empty_or_non_array_cases():
    for payload, code in ((None, "required"), ([], "empty_cases"), ({}, "invalid_cases_type")):
        result = tools.build_suite(payload)
        _assert_error_shape(result)
        assert result["errors"][0]["path"] == "cases"
        assert result["errors"][0]["code"] == code


def test_build_suite_rejects_yaml_text_or_any_non_object_case():
    result = tools.build_suite(["id: YAML-1", _case("OK-1")])

    _assert_error_shape(result)
    assert result["errors"] == [
        {
            "case_index": 0,
            "case_id": None,
            "path": "",
            "code": "invalid_case_type",
            "message": "用例必须是 JSON 对象",
        }
    ]


def test_build_suite_fails_whole_suite_and_keeps_all_structured_validation_errors():
    result = tools.build_suite([_case("OK-1"), {"id": "BAD-1", "title": "missing steps"}])

    _assert_error_shape(result)
    assert any(
        error["case_index"] == 1
        and error["case_id"] == "BAD-1"
        and error["path"] == "steps"
        and error["code"] == "schema"
        for error in result["errors"]
    )


def test_build_suite_rejects_duplicate_case_ids_without_partial_suite():
    result = tools.build_suite([_case("DUP-1"), _case("DUP-1")])

    _assert_error_shape(result)
    assert result["errors"] == [
        {
            "case_index": 1,
            "case_id": "DUP-1",
            "path": "id",
            "code": "duplicate_id",
            "message": "用例 id 与 cases[0] 重复",
        }
    ]


def test_build_suite_reports_non_blocking_warnings_for_runtime_risks():
    """契约合法但很可能跑不过的用例：仍能生成套件，但要带上 warnings 让 agent 自查。"""
    risky = {
        "id": "RISKY-1",
        "title": "risky",
        "steps": [
            {"id": "click-1", "action": "playwright.click", "args": {"target": "#go"}},
            {"id": "sleep-1", "action": "playwright.wait_for", "args": {"time": 3}},
        ],
        "assertions": [
            {"id": "a1", "type": "equals", "actual": "{{ steps.click-1 }}", "expected": "x"}
        ],
    }
    result = tools.build_suite([risky])

    assert result["ok"] is True, result["errors"]
    assert result["suite"] == {"cases": [risky | {"schema_version": 1}]}
    assert result["errors"] == []
    assert {warning["code"] for warning in result["warnings"]} == {
        "no_navigate",
        "fixed_sleep",
        "no_evidence",
        "whole_step_actual",
    }
    assert all(
        set(warning) == {"case_index", "case_id", "path", "code", "message"}
        and warning["case_id"] == "RISKY-1"
        for warning in result["warnings"]
    )


def test_build_suite_skips_warnings_while_schema_is_broken():
    """结构不合法时只给 errors（此时不猜 warnings），修完 errors 再按 warnings 收尾。"""
    broken = {
        "id": "BROKEN-1",
        "title": "broken",
        "priority": "P9",  # 非法枚举 → 阻断错误
        "steps": [{"id": "s1", "action": "playwright.close", "args": {}}],
    }

    result = tools.build_suite([broken])

    _assert_error_shape(result)
    assert result["warnings"] == []
    assert any(error["code"] == "schema" for error in result["errors"])
