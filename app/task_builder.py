"""把结构化步骤转成自然语言 task 文本。

作为「结构化 YAML → 现可跑通的自然语言 task」的适配层，保持执行侧行为与
原 uat-login.py 一致。登录 URL 由全局配置注入，不出现在用例中。
"""

from __future__ import annotations

from typing import Optional

from .case_loader import Case, Step


def _fmt_locator(locator: Optional[dict]) -> str:
    """把可选 locator 转成自然语言补充（用于兜底定位提示）。"""
    if not locator:
        return ""
    parts = []
    if locator.get("placeholder"):
        parts.append(f"placeholder 为『{locator['placeholder']}』")
    if locator.get("id"):
        parts.append(f"HTML id 为 {locator['id']}")
    if locator.get("role"):
        parts.append(f"role 为 {locator['role']}")
    if locator.get("class_name"):
        parts.append(f"class 为 {locator['class_name']}")
    if not parts:
        return ""
    return "（" + "，".join(parts) + "）"


def _step_text(step: Step) -> str:
    """单个步骤 -> 自然语言句子。"""
    loc = _fmt_locator(step.locator)
    p = step.params or {}

    if step.action == "goto":
        return f"打开页面 {p.get('url', step.target)} 并等待加载完成。"

    if step.action == "input":
        place = loc if loc else f"『{step.target}』"
        return f"在 {place} 的输入框中填入 {p.get('value', '')}。"

    if step.action == "click":
        return f"点击『{step.target}』{loc}。"

    if step.action == "select_option":
        return f"找到『{step.target}』，点击展开后选择『{p.get('option', '')}』选项。"

    if step.action == "hover":
        extra = p.get("note", "")
        return f"找到并把鼠标移到『{step.target}』上{extra}。"

    if step.action == "check":
        negative = bool(p.get("negative", False))
        if negative:
            return f"不要勾选『{step.target}』。"
        return f"勾选『{step.target}』。"

    if step.action == "verify":
        return f"等待并确认：{p.get('expect', step.target)}。"

    if step.action == "conclude":
        return p.get("text", f"输出结论：{step.target}")

    # 兜底：直接输出 target
    return step.target


def build_task(case: Case, login_url: str) -> str:
    """把用例转成自然语言 task 文本。

    Args:
        case: 用例对象。
        login_url: 当前平台的登录 URL（从平台配置注入，用例中不出现）。
    """
    lines: list[str] = []
    has_conclude = False
    for i, step in enumerate(case.steps, start=1):
        # goto 步骤的 URL 若未在 params 中指定，则用当前平台的 login_url
        if step.action == "goto" and not (step.params or {}).get("url"):
            step = step.model_copy(update={"params": {**step.params, "url": login_url}})
        lines.append(f"{i}. {_step_text(step)}")
        if step.action == "conclude":
            has_conclude = True

    # 性能优化：conclude 后追加"立即结束"强提示，避免 agent 反复"再检查/再确认"
    # 导致大 DOM 场景下每步 LLM 超时累计。
    if has_conclude:
        lines.append("")
        lines.append(
            "【强约束】完成上面『conclude』步骤后，**必须立即调用 done 动作结束任务**。"
            "不要再做任何额外点击/查询/截图/确认操作。LLM 输出尽量短（<=200 字），"
            "避免不必要的长思考导致大 DOM 场景下的超时重试。"
        )
    return "\n".join(lines)
