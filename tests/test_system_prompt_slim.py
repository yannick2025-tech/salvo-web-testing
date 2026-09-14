"""精简版 system prompt（C2）单元测试。"""

from importlib.resources import files

from browser_use_ext.system_prompt_slim import SLIM_SYSTEM_PROMPT, build_slim_system_prompt


def test_build_replaces_max_actions():
    prompt = build_slim_system_prompt(7)
    assert "{max_actions}" not in prompt
    assert "maximum of 7 actions" in prompt


def test_slim_removes_redundant_sections():
    assert "<file_system>" not in SLIM_SYSTEM_PROMPT
    assert "<planning>" not in SLIM_SYSTEM_PROMPT
    assert "<browser_vision>" not in SLIM_SYSTEM_PROMPT
    assert "<examples>" not in SLIM_SYSTEM_PROMPT


def test_slim_keeps_core_sections():
    for tag in (
        "<output>",
        "<action_rules>",
        "<browser_rules>",
        "<task_completion_rules>",
        "<efficiency_guidelines>",
        "<reasoning_rules>",
        "<critical_reminders>",
        "<error_recovery>",
        "<user_request>",
        "<agent_history>",
        "<browser_state>",
    ):
        assert tag in SLIM_SYSTEM_PROMPT, f"缺少 {tag}"


def test_slim_shorter_than_default():
    default = (
        files("browser_use.agent.system_prompts")
        .joinpath("system_prompt.md")
        .read_text(encoding="utf-8")
    )
    assert len(SLIM_SYSTEM_PROMPT) < len(default)
    # 预期下降显著（删掉 examples/file_system/planning/browser_vision）
    assert len(SLIM_SYSTEM_PROMPT) < len(default) * 0.75
