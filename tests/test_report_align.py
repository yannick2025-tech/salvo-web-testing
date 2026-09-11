"""对齐模块单元测试。"""

from types import SimpleNamespace

from app.report.align import (
    _match_texts,
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
    subs = [_ss(["totally_unknown_xyz"])]  # 真正未知动作，匹配失败
    steps, unaligned = align(subs, case)
    assert steps[0].substeps == []
    assert len(unaligned) == 1


def test_align_aux_action_attached_to_current_step():
    """scroll / wait 等辅助动作归到当前正在执行的用例步骤，不归 unaligned。"""
    case = [_case_step("click", "查询")]
    subs = [
        _ss(["scroll"]),  # 辅助动作（不归 unaligned）
        _ss(["click_element"], target_text="查询"),
    ]
    steps, unaligned = align(subs, case)
    assert len(steps[0].substeps) == 2  # scroll + click 都归到当前步骤
    assert unaligned == []


def test_align_aux_action_attached_when_no_current_match():
    """辅助动作在当前/下一步都匹配失败时，也归到当前步骤。"""
    case = [_case_step("click", "查询")]
    subs = [_ss(["scroll_down"])]  # 辅助：既不匹配当前也不匹配下一步
    steps, unaligned = align(subs, case)
    assert len(steps[0].substeps) == 1
    assert unaligned == []


def test_align_empty_target_text_fallback():
    """空目标文本的主操作：归当前步骤并推进（避免全归第一步 + unaligned 堆积）。"""
    case = [
        _case_step("click", "订单管理"),
        _case_step("click", "充电订单管理"),
        _case_step("click", "查询"),
    ]
    subs = [
        _ss(["click_element"]),  # 空 target_text 的 click
        _ss(["click_element"]),  # 空 target_text 的 click
        _ss(["click_element"]),  # 空 target_text 的 click
    ]
    steps, unaligned = align(subs, case)
    # 三个空 text click 各归一步（一个推进一步），不再 unaligned
    assert unaligned == []
    assert len(steps[0].substeps) == 1
    assert len(steps[1].substeps) == 1
    assert len(steps[2].substeps) == 1


def test_align_exact_match_advances_pointer():
    """精确匹配后推进 case_idx，使后续空文本子步骤落到正确的下一步。"""
    case = [
        _case_step("click", "订单管理"),
        _case_step("click", "充电订单管理"),
        _case_step("click", "查询"),
    ]
    subs = [
        _ss(["click_element"], target_text="订单管理"),      # 精确匹配 #01
        _ss(["click_element"]),                              # 空文本 → #02
        _ss(["click_element"]),                              # 空文本 → #03
    ]
    steps, unaligned = align(subs, case)
    assert unaligned == []
    assert steps[0].substeps[0].target_text == "订单管理"
    assert steps[1].substeps[0].target_text == ""
    assert steps[2].substeps[0].target_text == ""


def test_align_empty_target_text_advance_pointer():
    """空目标文本归当前后会推进 case_idx，让后续空 text 子步骤归到下一步。"""
    case = [
        _case_step("click", "充电订单管理"),
        _case_step("click", "充电订单详情"),
    ]
    subs = [
        _ss(["click_element"]),
        _ss(["click_element"], target_text="充电订单详情"),  # 有文本：应匹配 #02
    ]
    steps, unaligned = align(subs, case)
    # 第 1 个空 text click 归 #00 并推进到 #01；
    # 第 2 个有文本的 click 匹配 #01。
    assert unaligned == []
    assert len(steps[0].substeps) == 1
    assert len(steps[1].substeps) == 1
    assert steps[0].substeps[0].target_text == ""
    assert steps[1].substeps[0].target_text == "充电订单详情"


def test_match_texts_startswith_accepts_extension():
    """target 是元素文本的前缀（简化词）应匹配：如「查询」→「查询按钮」。"""
    ss = _ss(["click_element"], target_text="查询按钮")
    assert _match_texts(ss, "查询", []) is True


def test_match_texts_startswith_rejects_parent_menu():
    """target 是元素文本的后缀（父菜单）应拒绝：如「订单管理」≠「充电订单管理」。"""
    ss = _ss(["click_element"], target_text="充电订单管理")
    assert _match_texts(ss, "订单管理", []) is False


def test_match_texts_keyword_overlap_accepts():
    """拆词后有共同关键词（长度>=2）应匹配：如「城市名称」vs「请选择城市」。"""
    ss = _ss(["click_element"], target_text="请选择城市")
    assert _match_texts(ss, "城市名称", []) is True


def test_match_texts_keyword_overlap_rejects_no_common():
    """无共同关键词应拒绝。"""
    ss = _ss(["click_element"], target_text="其他内容")
    assert _match_texts(ss, "城市名称", []) is False


def test_align_extension_text_lands_on_step():
    """element_text 是 target 扩展（如「查询按钮」vs「查询」）应归到对应 case 步骤。"""
    case = [_case_step("click", "查询")]
    subs = [_ss(["click_element"], target_text="查询按钮")]
    steps, unaligned = align(subs, case)
    assert unaligned == []
    assert len(steps[0].substeps) == 1
    assert steps[0].substeps[0].target_text == "查询按钮"


def test_align_keyword_overlap_lands_on_step():
    """element_text 与 target 关键词重叠应归到对应 case 步骤。"""
    case = [_case_step("click", "城市名称")]
    subs = [_ss(["click_element"], target_text="请选择城市")]
    steps, unaligned = align(subs, case)
    assert unaligned == []
    assert len(steps[0].substeps) == 1


def test_align_falls_back_to_llm_intent_text():
    """元素文本不匹配但 LLM next_goal 含 target（如按钮文案"确定"但意图"点击查询"）应归到对应步骤。"""
    case = [_case_step("click", "查询")]
    # 元素文本"确定"与"查询"无文本重叠，但 next_goal 含"查询"
    ss = _ss(["click_element"], target_text="确定")
    ss.next_goal = "点击查询按钮查看充电订单"
    steps, unaligned = align([ss], case)
    assert unaligned == []
    assert len(steps[0].substeps) == 1
    assert steps[0].substeps[0].target_text == "确定"
