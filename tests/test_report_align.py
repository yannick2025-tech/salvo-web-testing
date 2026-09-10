"""对齐模块单元测试。"""

from types import SimpleNamespace

from app.report.align import (
    _text_from_element,
    action_category,
    align,
)
from app.report.models import ReportSubStep


def _ss(action_names, target_text="", success=True, next_goal="", evaluation=""):
    return ReportSubStep(
        index=1,
        action_names=action_names,
        target_text=target_text,
        success=success,
        next_goal=next_goal,
        evaluation=evaluation,
    )


def _case_step(action, target, **params):
    return SimpleNamespace(action=action, target=target, params=params)


def test_action_category_mapping():
    assert action_category("go_to_url") == "goto"
    assert action_category("input_text") == "input"
    assert action_category("click_element") == "click"
    assert action_category("hover_element") == "hover"
    assert action_category("select_dropdown_option") == "select_option"
    assert action_category("done") == "conclude"
    assert action_category("unknown_action") == "unknown_action"


def test_text_from_element_priority():
    el = SimpleNamespace(ax_name="", attributes={"placeholder": "请输入账号"}, node_value="")
    assert _text_from_element(el) == "请输入账号"

    el2 = SimpleNamespace(ax_name="登录按钮", attributes={}, node_value="")
    assert _text_from_element(el2) == "登录按钮"

    assert _text_from_element(None) == ""


def test_align_goto_then_click():
    case = [_case_step("goto", "登录页"), _case_step("click", "登录按钮")]
    subs = [_ss(["go_to_url"]), _ss(["click_element"], target_text="登录按钮")]
    steps, unaligned = align(subs, case)
    assert len(steps) == 2
    assert len(steps[0].substeps) == 1
    assert len(steps[1].substeps) == 1
    assert unaligned == []


def test_align_one_step_multiple_substeps():
    case = [_case_step("select_option", "单据时间", option="订单创建时间")]
    subs = [
        _ss(["click_element"], target_text="单据时间"),
        _ss(["click_element"], target_text="订单创建时间"),
    ]
    steps, unaligned = align(subs, case)
    assert len(steps[0].substeps) == 2
    assert unaligned == []


def test_align_verify_matches_next_goal():
    case = [_case_step("verify", "登录成功", expect="已跳转到后台首页")]
    subs = [_ss(["done"], next_goal="确认已跳转到后台首页")]
    steps, unaligned = align(subs, case)
    assert len(steps[0].substeps) == 1


def test_align_unaligned_fallback():
    case = [_case_step("click", "查询")]
    subs = [_ss(["scroll_down"])]  # 未知动作，无法匹配
    steps, unaligned = align(subs, case)
    assert steps[0].substeps == []
    assert len(unaligned) == 1
