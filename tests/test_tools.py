"""Tests for the single JSON suite-building operation."""

from __future__ import annotations

from mtp_contracts_mcp import tools


def _case(case_id: str) -> dict:
    return {
        "id": case_id,
        "title": f"case {case_id}",
        "steps": [{"id": "s1", "action": "playwright.snapshot"}],
    }


def _assert_error_shape(result: dict) -> None:
    assert set(result) == {"ok", "suite", "errors"}
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
