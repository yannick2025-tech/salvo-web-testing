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


# 辅助动作：scroll / wait / 读文件 等不是用例语义步骤的 LLM 操作。
# 对齐时归到当前正在进行的用例步骤（不归 unaligned），且不参与 judge。
_AUX_ACTIONS = frozenset({
    "scroll", "scroll_down", "scroll_up", "wait",
    "send_keys", "press_key", "read_file", "write_file",
    "extract_content", "search_page", "find_text",
    "evaluate",  # browser-use 的 JS 评估（检查页面状态），归当前不推进
})


def is_aux_substep(ss: ReportSubStep) -> bool:
    """判断子步骤是否为辅助动作（不参与用例步骤成功/失败判定）。"""
    if not ss.action_names:
        return False
    n = ss.action_names[0]
    return n in _AUX_ACTIONS or n.startswith("scroll") or n.startswith("wait")


def _text_from_element(el: Any) -> str:
    """从 DOMInteractedElement 提取可读文本。

    优先 ax_name（可访问名称，最可靠），其次 attributes 里的常见文本字段，
    最后 node_value（text node 的内容）。如果全部为空，返回 ""，
    由 align 的空目标文本兜底分支处理。
    """
    if el is None:
        return ""
    ax_name = getattr(el, "ax_name", "") or ""
    if ax_name:
        return str(ax_name).strip()
    attrs = getattr(el, "attributes", None) or {}
    # 扩展候选：覆盖 browser-use / 各种 UI 框架（Element UI、Ant Design 等）
    # 把 text / innerText / aria-label / placeholder / title / alt / value /
    # data-text / data-label / label / name 都尝试一遍。
    for key in (
        "text", "innerText", "textContent",
        "aria-label", "title", "placeholder", "alt", "value",
        "data-text", "data-label", "label", "name",
    ):
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

    接受以下任一情况（避免父菜单「订单管理」误吞子菜单「充电订单管理」）：
    - 精确相等
    - 元素文本是 target 的子串（ss 在 c 里）—— target 是元素文本的更具体形式
    - target 是元素文本的前缀（ss 以 c 开头）—— target 是元素文本的简化/截断
      （如「查询」→「查询按钮」接受；「订单管理」→「充电订单管理」因不以
      「订单管理」开头而拒绝）
    - 拆词后有共同关键词（长度 >= 2）—— 处理「城市名称」vs「请选择城市」
      这类语义相同但文本不同的情况

    父菜单后缀排除：c 是 ss 的真后缀但不是前缀（如「订单管理」是
    「充电订单管理」的后缀），直接跳过该 c，避免关键词重叠误判。
    """
    for c in [target] + list(extra_texts):
        if not c:
            continue
        c = str(c).strip()
        if not c or not ss.target_text:
            continue
        # 父菜单后缀排除：c 是 ss 的后缀但不是前缀 → 父菜单误吞，跳过
        if ss.target_text.endswith(c) and not ss.target_text.startswith(c):
            continue
        if c == ss.target_text:
            return True
        if ss.target_text in c:
            return True
        if ss.target_text.startswith(c):
            return True
        # 关键词重叠：双方拆词（含 2-gram）后有共同词
        c_set = set(p for p in _fragments(c) if len(p) >= 2)
        ss_set = set(p for p in _fragments(ss.target_text) if len(p) >= 2)
        if c_set and ss_set and (c_set & ss_set):
            return True
    return False


def _fragments(text: str) -> list[str]:
    """把句子按常见分隔符拆成关键词片段，并对中文连写片段补 2-gram 拆字。

    例：「城市名称」→ ["城市名称", "城市", "市名", "名称"]，
    与「请选择城市」→ ["请选择城市", "请选", "选择", "择城", "城市"]
    共享 "城市"，用于关键词重叠匹配。
    """
    import re

    base = [p for p in re.split(r"[/、，,。；;\s]+", text) if p]
    extra: list[str] = []
    for seg in base:
        if len(seg) >= 2:
            for i in range(len(seg) - 1):
                extra.append(seg[i : i + 2])
    return base + extra


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


def _text_match_fallback(
    ss: ReportSubStep, target: str, extra_texts: list[str]
) -> bool:
    """元素文本匹配 → 失败时用 LLM 的 thinking / next_goal / evaluation 宽松匹配。

    解决「元素文本与 target 不完全一致但 LLM 意图里包含 target」的场景
    （如 element_text="确定" 而 case 写"查询"，但 LLM thinking="点击查询按钮
    查看订单"）。三个字段都试，合并去空。
    """
    if _match_texts(ss, target, extra_texts):
        return True
    intent = " ".join(s for s in (ss.thinking, ss.next_goal, ss.evaluation) if s)
    if intent.strip():
        return _loose_match(intent, target, extra_texts)
    return False


def _matches(ss: ReportSubStep, action: str, target: str, extra_texts: list[str]) -> bool:
    """判断子步骤是否属于某个用例步骤。"""
    cat = action_category(ss.action_names[0]) if ss.action_names else ""

    # goto：无元素文本，按类别匹配
    if action == "goto" and cat == "goto":
        return True

    # input / hover：类别匹配，有文本时用文本（精确+宽松）区分
    if action in ("input", "hover") and cat == action:
        if ss.target_text:
            return _text_match_fallback(ss, target, extra_texts)
        return True

    # click 家族：click / select_option / check 都由 click 构成，需文本辅助。
    # 空目标文本不在此兜底（由 align 的"空文本主操作归当前+推进"处理，
    # 避免所有空文本 click 全归第一步）。
    if action in ("click", "select_option", "check") and cat in (
        "click",
        "select_option",
        "check",
    ):
        return _text_match_fallback(ss, target, extra_texts)

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
    _MAIN_CATS = ("click", "input", "hover", "select_option", "check", "goto")
    for ss in substeps:
        if case_idx >= len(steps):
            unaligned.append(ss)
            continue
        cat = action_category(ss.action_names[0]) if ss.action_names else ""
        a, t, extra = meta[case_idx]
        advance = meta[case_idx][0] != "select_option"  # 匹配后是否推进

        # 1) 尝试匹配当前步骤（含 LLM 意图文本兜底）
        if _matches(ss, a, t, extra):
            steps[case_idx].substeps.append(ss)
            if advance:
                case_idx += 1
            continue
        # 2) 尝试匹配下一步
        if case_idx + 1 < len(steps):
            na, nt, nextra = meta[case_idx + 1]
            if _matches(ss, na, nt, nextra):
                case_idx += 1
                steps[case_idx].substeps.append(ss)
                if meta[case_idx][0] != "select_option":
                    case_idx += 1
                continue
        # 3) 辅助动作（scroll/wait/evaluate 等）：归当前不推进
        if is_aux_substep(ss):
            steps[case_idx].substeps.append(ss)
            continue
        # 4) 已知主操作（click/input/hover/select_option/check/goto）未匹配任何
        #    步骤：按顺序归当前并推进（启发式兜底，避免 unaligned 堆积导致
        #    后续步骤错位"该步骤未执行"）
        if cat in _MAIN_CATS:
            steps[case_idx].substeps.append(ss)
            if advance:
                case_idx += 1
            continue
        # 5) 真正不匹配（未知 cat，如 evaluate/search 等）→ unaligned
        unaligned.append(ss)
    return steps, unaligned
