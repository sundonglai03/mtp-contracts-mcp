"""工具说明必须与共用契约一致。

agent 是套件的唯一作者，而它只能读到工具说明 —— 说明里写错，agent 就照着写错
（评审里出现过：示例教人用 on_failure: continue 当「可选」，实际会让用例判失败）。
所以把两件事钉死：

- 说明书里的最小示例必须自己就是「通过校验 + 零 warnings」；
- 说明书里的断言表必须与 core 的断言目录对得上（类型 + 必填字段）。
"""

from __future__ import annotations

import json
import re

from mtp_contracts.assertion_catalog import ASSERTIONS, known_types
from mtp_contracts_mcp import server, tools


def test_documented_minimal_example_builds_without_warnings():
    example = json.loads(server.MINIMAL_EXAMPLE)
    result = tools.build_suite([example])

    assert result["ok"] is True, result["errors"]
    assert result["warnings"] == [], "说明书示例自身带 warnings，agent 照抄就会踩坑"


def test_documented_assertion_table_matches_the_shared_catalog():
    lines = server.INSTRUCTIONS.splitlines()
    for assertion_type in known_types():
        spec = ASSERTIONS[assertion_type]
        required = [name.split(".")[-1] for name in spec.requires]
        # 「至少给一个」的那几组也要出现在说明里，否则 agent 不知道还有别的写法
        any_groups = [
            [name.split(".")[-1] for name in group] for group in spec.requires_any
        ]
        candidates = [row for row in lines if re.search(rf"\b{assertion_type}\b", row)]
        assert candidates, f"说明书里没有断言 {assertion_type} 的说明"
        assert any(all(key in row for key in required) for row in candidates), (
            f"说明书里 {assertion_type} 的说明没写清必填字段 {required}：{candidates}"
        )
        for group in any_groups:
            if not group:
                continue
            assert any(
                any(key in row for key in group) for row in candidates
            ), f"说明书里 {assertion_type} 的说明没写清「至少一个」字段 {group}：{candidates}"
