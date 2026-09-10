"""LLM 执行步骤 -> YAML 用例步骤的对齐（方案 A：离线序列对齐）。

`extract_substeps` 把 browser-use 的 history 转成 ReportSubStep 列表（纯数据），
`align` 把子步骤列表映射回用例步骤。两者分离，便于单元测试。
"""

from __future__ import annotations

from typing import Any, Optional

from .models import ReportSubStep, ReportStep

# LLM 动作名 -> 用例动作类别
_ACTION_CATEGORY = {
    "go_to_url": "goto",
    "navigate": "goto",
    "input_text": "input",
    "click_element": "click",
    "hover_element": "hover",
    "select_dropdown_option": "select_option",
    "select_option": "select_option",
    "done": "conclude",
    "finish": "conclude",
    "check_element": "check",
    "uncheck_element": "check",
}

# 动作名 -> 人类可读中文描述
_ACTION_LABEL = {
    "go_to_url": "打开页面",
    "navigate": "打开页面",
    "input_text": "输入",
    "click_element": "点击",
    "hover_element": "悬停",
    "select_dropdown_option": "选择下拉项",
    "done": "结束",
    "check_element": "勾选",
    "uncheck_element": "取消勾选",
}


def action_category(action_name: str) -> str:
    """把 LLM 动作名映射为用例动作类别；未知动作返回原始名。"""
    return _ACTION_CATEGORY.get(action_name, action_name)


def _text_from_element(el: Any) -> str:
    """从 DOMInteractedElement 提取可读文本。"""
    if el is None:
        return ""
    ax_name = getattr(el, "ax_name", "") or ""
    if ax_name:
        return str(ax_name).strip()
    attrs = getattr(el, "attributes", None) or {}
    for key in ("value", "aria-label", "title", "placeholder", "alt"):
        v = attrs.get(key)
        if v:
            return str(v).strip()
    node_value = getattr(el, "node_value", "") or ""
    return str(node_value).strip()


def _action_info(agent_output: Any) -> tuple[list[str], str]:
    """从 AgentOutput 提取动作名列表与动作人类可读描述。"""
    names: list[str] = []
    descs: list[str] = []
    try:
        actions = getattr(agent_output, "action", None) or []
        for action_model in actions:
            dump = (
                action_model.model_dump(exclude_unset=True)
                if hasattr(action_model, "model_dump")
                else {}
            )
            for name, params in dump.items():
                names.append(name)
                label = _ACTION_LABEL.get(name, name)
                if isinstance(params, dict):
                    parts = [label]
                    for k in ("text", "value", "url", "option", "text_to_check"):
                        if params.get(k):
                            parts.append(str(params[k]))
                    descs.append(" ".join(parts))
                else:
                    descs.append(label)
    except Exception:
        pass
    return names, "; ".join(descs)


def _interacted_text(state: Any) -> str:
    """从 BrowserStateHistory.interacted_element 提取首个非空元素文本。"""
    interacted = getattr(state, "interacted_element", None) or []
    for el in interacted:
        t = _text_from_element(el)
        if t:
            return t
    return ""


def _substep_success(result: Any) -> tuple[bool, Optional[str]]:
    """从 AgentHistory.result 判断该子步骤是否成功，并提取错误信息。"""
    success = True
    error: Optional[str] = None
    try:
        for r in result or []:
            if getattr(r, "error", None):
                error = str(r.error)
                success = False
                break
            if getattr(r, "success", None) is False:
                success = False
    except Exception:
        pass
    return success, error


def _substep_screenshot(state: Any) -> Optional[str]:
    """取子步骤截图（base64）。优先调用 get_screenshot()，兼容 BrowserStateSummary。"""
    if state is None:
        return None
    gs = getattr(state, "get_screenshot", None)
    if callable(gs):
        try:
            return gs()  # base64 str 或 None
        except Exception:
            return None
    return getattr(state, "screenshot", None) or None


def _substep_duration(metadata: Any) -> Optional[float]:
    """取子步骤耗时（秒）。"""
    if metadata is None:
        return None
    d = getattr(metadata, "duration_seconds", None)
    if callable(d):
        try:
            return float(d())
        except Exception:
            pass
    d = getattr(metadata, "step_interval", None)
    if d is not None:
        try:
            return float(d)
        except (TypeError, ValueError):
            pass
    return None


def extract_substeps(history: Any) -> list[ReportSubStep]:
    """把 AgentHistoryList 转成 ReportSubStep 列表。"""
    substeps: list[ReportSubStep] = []
    try:
        items = getattr(history, "history", None) or []
    except Exception:
        return substeps

    for i, item in enumerate(items, start=1):
        mo = getattr(item, "model_output", None)
        state = getattr(item, "state", None)
        result = getattr(item, "result", None)
        metadata = getattr(item, "metadata", None)

        names, desc = _action_info(mo)
        success, error = _substep_success(result)

        substeps.append(
            ReportSubStep(
                index=i,
                action_names=names,
                action_desc=desc,
                target_text=_interacted_text(state),
                success=success,
                error=error,
                thinking=(getattr(mo, "thinking", None) or ""),
                next_goal=(getattr(mo, "next_goal", None) or ""),
                evaluation=(getattr(mo, "evaluation_previous_goal", None) or ""),
                url=(getattr(state, "url", None) or ""),
                title=(getattr(state, "title", None) or ""),
                screenshot=_substep_screenshot(state),
                duration=_substep_duration(metadata),
            )
        )
    return substeps


def _match_texts(ss: ReportSubStep, target: str, extra_texts: list[str]) -> bool:
    """判断子步骤与用例步骤的文本是否相关。

    仅允许「精确相等」或「元素文本是 target 的子串」两种方向；不允许
    「target 是元素文本的真子串」，否则父菜单（如「订单管理」）会误吞
    子菜单（如「充电订单管理」）。
    """
    for c in [target] + list(extra_texts):
        if not c:
            continue
        c = str(c).strip()
        if not c:
            continue
        if c == ss.target_text:
            return True
        if ss.target_text and ss.target_text in c:
            return True
    return False


def _fragments(text: str) -> list[str]:
    """把句子按常见分隔符拆成关键词片段，用于宽松匹配。"""
    import re

    return [p for p in re.split(r"[/、，,。；;\s]+", text) if p]


def _loose_match(text: str, target: str, extra_texts: list[str]) -> bool:
    """宽松文本匹配：完整串或拆分片段命中即算匹配。"""
    for c in [target] + list(extra_texts):
        if not c:
            continue
        c = str(c).strip()
        if not c:
            continue
        if c in text:
            return True
        for frag in _fragments(c):
            if frag and frag in text:
                return True
    return False


def _matches(ss: ReportSubStep, action: str, target: str, extra_texts: list[str]) -> bool:
    """判断子步骤是否属于某个用例步骤。"""
    cat = action_category(ss.action_names[0]) if ss.action_names else ""

    # goto：无元素文本，按类别匹配
    if action == "goto" and cat == "goto":
        return True

    # input / hover：类别匹配，有文本时用文本区分（避免连续同类别步骤误吞）
    if action in ("input", "hover") and cat == action:
        if ss.target_text:
            return _match_texts(ss, target, extra_texts)
        return True

    # click 家族：click / select_option / check 都由 click 构成，需文本辅助
    if action in ("click", "select_option", "check") and cat in (
        "click",
        "select_option",
        "check",
    ):
        return _match_texts(ss, target, extra_texts) or not ss.target_text

    # verify：其 LLM 子步骤通常是 done（conclude 类别），直接按类别匹配；
    # 非 done 时退回 next_goal/evaluation 宽松关键词匹配。
    if action == "verify":
        if cat == "conclude":
            return True
        text = ss.next_goal or ss.evaluation or ""
        return _loose_match(text, target, extra_texts)

    # conclude：done 动作
    if action == "conclude" and cat == "conclude":
        return True

    return False


def align(
    substeps: list[ReportSubStep], case_steps: list[Any]
) -> tuple[list[ReportStep], list[ReportSubStep]]:
    """贪心序列对齐。返回 (报告步骤列表, 未归类子步骤列表)。"""
    steps: list[ReportStep] = []
    meta: list[tuple[str, str, list[str]]] = []  # (action, target, extra_texts)

    for i, cs in enumerate(case_steps, start=1):
        action = getattr(cs, "action", "") or ""
        target = getattr(cs, "target", "") or ""
        params = getattr(cs, "params", None) or {}
        extra = [
            str(params[k])
            for k in ("option", "value", "expect", "text")
            if params.get(k)
        ]
        meta.append((action, target, extra))
        steps.append(ReportStep(index=i, action=action, target=target))

    unaligned: list[ReportSubStep] = []
    case_idx = 0
    for ss in substeps:
        if case_idx >= len(steps):
            unaligned.append(ss)
            continue
        a, t, extra = meta[case_idx]
        if _matches(ss, a, t, extra):
            steps[case_idx].substeps.append(ss)
        elif case_idx + 1 < len(steps):
            na, nt, nextra = meta[case_idx + 1]
            if _matches(ss, na, nt, nextra):
                case_idx += 1
                steps[case_idx].substeps.append(ss)
            else:
                unaligned.append(ss)
        else:
            unaligned.append(ss)
    return steps, unaligned
