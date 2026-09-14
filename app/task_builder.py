"""把结构化步骤转成自然语言 task 文本。

作为「结构化 YAML → 现可跑通的自然语言 task」的适配层，保持执行侧行为与
原 uat-login.py 一致。登录 URL 由全局配置注入，不出现在用例中。
"""

from __future__ import annotations

from typing import Optional

from .case_loader import Case, Step

# 复用 auto_apply 的日期窗口计算原语，保证「相对窗口」的解析规则与设值侧一致。
from browser_use_ext.memory.auto_apply import compute_date_window
from browser_use_ext.memory.models import ElementMemoryConfig


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

    if step.action == "set_date_range":
        start = p.get("start")
        end = p.get("end")
        if start and end:
            return f"将『{step.target}』日期范围设为 {start} ~ {end}。"
        db = p.get("days_back", 10)
        it = bool(p.get("include_today", False))
        desc = "含今天" if it else "不含今天"
        return f"将『{step.target}』日期范围设为过去 {db} 天（{desc}）的窗口。"

    if step.action == "verify":
        return f"等待并确认：{p.get('expect', step.target)}。"

    if step.action == "conclude":
        return p.get("text", f"输出结论：{step.target}")

    # 兜底：直接输出 target
    return step.target


def build_steps_task(steps: list[Step], login_url: str) -> str:
    """把一组步骤转成自然语言 task 文本（setup 与单个 case 通用）。

    Args:
        steps: 步骤列表。
        login_url: 当前平台的登录 URL（goto 步骤的 URL 缺省时注入）。
    """
    lines: list[str] = []
    has_conclude = False
    for i, step in enumerate(steps, start=1):
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


def build_task(case: Case, login_url: str) -> str:
    """把用例转成自然语言 task 文本（向后兼容：等价于 build_steps_task(case.steps)）。

    Args:
        case: 用例对象。
        login_url: 当前平台的登录 URL（从平台配置注入，用例中不出现）。
    """
    return build_steps_task(case.steps, login_url)


def extract_date_target(
    steps: list[Step],
    days_back: int = 10,
    include_today: bool = False,
) -> Optional[tuple[str, str]]:
    """从步骤中提取「日期范围目标」，归一化为 (start, end) 绝对日期。

    只有 `set_date_range` 步骤是日期目标的唯一来源（单一来源，避免启发式歧义）：
    - 固定区间：`params.start` / `params.end` 字面值（原样返回）。
    - 相对窗口：`params.days_back` / `params.include_today`，复用
      `compute_date_window` 立即算成绝对日期（今天在 agent 生命周期内不变）。

    Args:
        steps: 用例步骤列表。
        days_back: 相对窗口缺省「往前 N 天」（来自 config.date_range_days_back）。
        include_today: 相对窗口缺省「是否含今天」。

    Returns:
        (start, end) 绝对日期元组；无 `set_date_range` 步骤时返回 None。
    """
    for step in steps:
        if step.action != "set_date_range":
            continue
        p = step.params or {}
        start = p.get("start")
        end = p.get("end")
        if start and end:
            return (str(start), str(end))
        db = int(p.get("days_back", days_back))
        it = bool(p.get("include_today", include_today))
        cfg = ElementMemoryConfig(date_range_days_back=db, date_range_include_today=it)
        return compute_date_window(cfg)
    return None
