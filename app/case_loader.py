"""YAML 测试用例加载。

两种格式：

1. 套件（suite）：`setup`（可选公共前置，如登录）+ `cases`（多个用例）。
2. 单用例（旧格式，向后兼容）：顶层直接 `steps`。

字段：
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
from pydantic import BaseModel, Field


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


class Suite(BaseModel):
    """一个测试套件：可选公共前置（setup）+ 多个用例（cases）。

    执行时 setup 只跑一次（如登录），随后各 case 复用同一浏览器会话依次执行。
    """

    name: str
    description: str = Field(default="")
    setup: list[Step] = Field(default_factory=list)
    cases: list[Case] = Field(default_factory=list)


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
    "set_date_range",
}


def _check_actions(steps: list[Step], where: str) -> None:
    """校验 steps 的 action 类型。where 用于错误信息前缀（如「setup 」「用例「x」」）。"""
    for i, step in enumerate(steps, start=1):
        if step.action not in ALLOWED_ACTIONS:
            raise ValueError(
                f"{where}第 {i} 步 action={step.action!r} 非法，允许: {sorted(ALLOWED_ACTIONS)}"
            )


def _read_data(path: str, extra: Optional[dict[str, str]] = None) -> dict[str, Any]:
    """读取 YAML 并展开环境变量占位符，返回顶层映射。

    extra 为额外的占位符映射（如平台级 ${ACCOUNT}/${PASSWORD}），优先于环境变量。
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"用例文件不存在: {p}")

    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    # 敏感信息脱敏：用例里的 ${VAR} 占位符替换为环境变量/extra 值（如账号/密码）。
    from .config import expand_env_vars

    data = expand_env_vars(data, extra)

    if not isinstance(data, dict):
        raise ValueError("用例文件顶层必须是映射")
    return data


def load_case(path: str) -> Case:
    """从 YAML 加载并校验单个测试用例（旧格式：顶层直接 steps）。"""
    data = _read_data(path)

    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("用例必须包含非空的 steps 列表")

    case = Case.model_validate(data)
    _check_actions(case.steps, "")
    return case


def load_suite(path: str, account: str = "", password: str = "") -> Suite:
    """从 YAML 加载一个套件。

    支持两种格式：
    - 套件：顶层含 `cases`（可选 `setup`），返回 Suite(setup, cases)。
    - 单用例（旧）：顶层只有 `steps`，返回 setup 为空的单用例套件。

    account / password 用于平台级凭据注入：把用例里的 `${ACCOUNT}` /
    `${PASSWORD}` 占位符替换为传入值（优先级高于环境变量），使不同平台的
    用例各用各的账号密码。不传时占位符保留原样。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: 结构非法 / 未知 action。
    """
    extra: dict[str, str] = {}
    if account or password:
        extra = {"ACCOUNT": account, "PASSWORD": password}
    data = _read_data(path, extra)

    if "cases" in data:
        setup = [Step.model_validate(s) for s in (data.get("setup") or [])]
        cases = [Case.model_validate(c) for c in data["cases"]]
        if not cases:
            raise ValueError("套件的 cases 不能为空")
        _check_actions(setup, "setup ")
        for c in cases:
            if not c.steps:
                raise ValueError(f"用例「{c.name}」必须包含非空的 steps 列表")
            _check_actions(c.steps, f"用例「{c.name}」")
        return Suite(
            name=data.get("name", ""),
            description=data.get("description", ""),
            setup=setup,
            cases=cases,
        )

    # 旧单用例格式：视为 setup 为空的单用例套件（直接用已展开的 data）
    steps = data.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("用例必须包含非空的 steps 列表")
    case = Case.model_validate(data)
    _check_actions(case.steps, "")
    return Suite(name=case.name, description=case.description, setup=[], cases=[case])
