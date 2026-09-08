"""工具精简（方案C1）单元测试。"""

from app.config import RunnerConfig
from browser_use import Tools

_DEFAULT_EXCLUDE = [
    "search",
    "upload_file",
    "save_as_pdf",
    "write_file",
    "replace_file",
    "read_file",
    "find_text",
    "close",
]


def test_runner_config_default_tool_exclude():
    rc = RunnerConfig()
    for name in _DEFAULT_EXCLUDE:
        assert name in rc.tool_exclude, f"{name} 应在默认排除清单"
    assert "navigate" not in rc.tool_exclude
    assert "click" not in rc.tool_exclude
    assert "input" not in rc.tool_exclude


def test_tools_exclude_actions():
    tools = Tools(exclude_actions=_DEFAULT_EXCLUDE)
    actions = tools.registry.registry.actions
    for name in _DEFAULT_EXCLUDE:
        assert name not in actions, f"{name} 应被排除"
    for name in ["navigate", "input", "wait", "scroll", "done", "click", "evaluate"]:
        assert name in actions, f"{name} 应保留"


def test_tools_no_exclude_keeps_all():
    tools = Tools(exclude_actions=None)
    actions = tools.registry.registry.actions
    assert "search" in actions
    assert "close" in actions
