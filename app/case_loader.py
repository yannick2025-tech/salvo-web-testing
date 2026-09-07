"""YAML 测试用例加载。

用例为结构化步骤列表，字段：
- action: 动作类型（goto/input/click/select_option/hover/check/verify/conclude）
- target: 意图描述（做什么）
- locator: 可选定位信息（优先从记忆取，用例中可省略）
- params: 动作参数（如 input 的 value、select_option 的 option、check 的 negative 等）

设计原则：locator 可省略，运行时定位顺序为「记忆命中 > 用例 locator > LLM 现场定位」。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field, ValidationError


class Step(BaseModel):
    """单个测试步骤。"""

    action: str
    target: str = ""  # conclude 等动作可无 target，用 params.text 代替
    locator: Optional[dict[str, Any]] = Field(default=None)
    params: dict[str, Any] = Field(default_factory=dict)


class Case(BaseModel):
    """一个测试用例。"""

    name: str
    description: str = Field(default="")
    steps: list[Step]


# 允许的 action 类型
ALLOWED_ACTIONS = {
    "goto",
    "input",
    "click",
    "select_option",
    "hover",
    "check",
    "verify",
    "conclude",
}


def load_case(path: str) -> Case:
    """从 YAML 加载并校验一个测试用例。

    Raises:
        FileNotFoundError: 文件不存在。
        ValidationError: 字段缺失/非法。
        ValueError: 出现未知 action 类型。
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"用例文件不存在: {p}")

    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # 敏感信息脱敏：用例里的 ${VAR} 占位符替换为环境变量值（如账号/密码）。
    from .config import expand_env_vars

    data = expand_env_vars(data)

    if not isinstance(data, dict):
        raise ValueError("用例文件顶层必须是映射")

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("用例必须包含非空的 steps 列表")

    case = Case.model_validate(data)

    # 校验 action 类型
    for i, step in enumerate(case.steps, start=1):
        if step.action not in ALLOWED_ACTIONS:
            raise ValueError(
                f"第 {i} 步 action={step.action!r} 非法，允许: {sorted(ALLOWED_ACTIONS)}"
            )

    return case
