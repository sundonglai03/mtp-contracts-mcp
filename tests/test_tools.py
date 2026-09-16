"""规范工具的单元测试（不依赖网络/MCP）。"""

from __future__ import annotations

from mtp_contracts_mcp import tools

VALID_CASE = {
    "schema_version": 1,
    "id": "OK-1",
    "title": "valid",
    "steps": [{"id": "s1", "action": "playwright.snapshot"}],
}

MISSING_STEPS = {
    "schema_version": 1,
    "id": "BAD-1",
    "title": "missing steps",
}

UNDECLARED_REF = {
    "schema_version": 1,
    "id": "BAD-REF",
    "title": "undeclared reference",
    "steps": [
        {
            "id": "s1",
            "action": "api.get",
            "args": {"url": "{{ vars.undefined }}"},
        }
    ],
}


def test_validate_valid_case_ok():
    result = tools.validate_one(VALID_CASE)
    assert result["ok"], result["issues"]
    assert result["issue_count"] == 0


def test_validate_invalid_case_has_paths():
    result = tools.validate_one(MISSING_STEPS)
    assert not result["ok"]
    assert result["issues"]
    assert all(i["path"] for i in result["issues"])


def test_validate_accepts_dict_input():
    case = {
        "schema_version": 1,
        "id": "OK-1",
        "title": "t",
        "steps": [{"id": "s1", "action": "playwright.snapshot"}],
    }
    assert tools.validate_one(case)["ok"]


def test_validate_suite_aggregates():
    suite = tools.validate_many(
        [
            VALID_CASE,
            UNDECLARED_REF,
        ]
    )
    assert suite["total"] == 2
    assert suite["passed"] == 1
    assert suite["failed"] == 1
    assert suite["ok"] is False


def test_validate_suite_reports_unparseable_input():
    suite = tools.validate_many(["- not-a-mapping"])
    assert suite["ok"] is False
    assert suite["results"][0]["issues"][0]["kind"] == "input"


def test_normalize_fills_defaults_and_strips_internal():
    result = tools.normalize_one({"id": "N-1", "_source": "/x", "steps": []})
    case = result["case"]
    assert case["schema_version"] == 1
    assert "_source" not in case
    assert case["assertions"] == []
    assert any("schema_version" in c for c in result["changes"])


def test_schema_info_shape():
    info = tools.schema_info()
    assert info["schema_version_supported"] == [1]
    assert isinstance(info["json_schema"], dict)
    assert info["json_schema"]


def test_explain_error_gives_hint():
    out = tools.explain_error("steps[0].action", "缺少必填字段", "schema")
    assert out["path"] == "steps[0].action"
    assert out["hint"]


def test_explain_error_plaintext_secret_hint():
    out = tools.explain_error("secrets.password", "禁止明文凭据", "security")
    assert "secrets" in out["hint"]


def test_parse_case_rejects_sequence():
    import pytest

    with pytest.raises(tools.CaseInputError):
        tools.parse_case("- a\n- b\n")
