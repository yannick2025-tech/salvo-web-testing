"""报告中间数据模型。

把一次运行的历史与用例映射后，统一用这里的模型表示，供对齐/判定/渲染使用。
与 browser-use 解耦：所有字段都是纯数据，便于单元测试。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class StepStatus(str, Enum):
    """用例步骤三态。"""

    SUCCESS = "success"  # 成功（绿）
    FAILED = "failed"  # 失败（红）
    SKIPPED = "skipped"  # 未执行（灰）


@dataclass
class ReportSubStep:
    """报告里的一个 LLM 执行子步骤。"""

    index: int  # 在 history 中的全局序号（1-based）
    action_names: list[str] = field(default_factory=list)  # LLM 动作名列表
    action_desc: str = ""  # 动作人类可读描述
    target_text: str = ""  # 被操作元素文本（从 interacted_element 反查）
    success: bool = True  # 该子步骤是否成功
    error: Optional[str] = None  # 错误信息
    thinking: str = ""
    next_goal: str = ""
    evaluation: str = ""
    url: str = ""
    title: str = ""
    screenshot: Optional[str] = None  # base64 截图数据
    screenshot_path: Optional[str] = None  # 落盘后的相对路径（screenshots/xxx.png）
    keep_screenshot: bool = True  # 是否保留截图（失败重试策略）
    duration: Optional[float] = None  # 耗时（秒）


@dataclass
class ReportStep:
    """报告里的一个 YAML 用例步骤。"""

    index: int  # 用例步骤序号（1-based）
    action: str  # 用例动作（goto/input/click/...）
    target: str  # 用例 target
    status: StepStatus = StepStatus.SKIPPED
    substeps: list[ReportSubStep] = field(default_factory=list)
    aligned: bool = True  # 是否精确对齐


@dataclass
class ReportCase:
    """一次运行的报告数据。"""

    name: str = ""
    description: str = ""
    overall_success: Optional[bool] = None  # 整体成功/失败/None(未完成)
    final_result: str = ""
    steps: list[ReportStep] = field(default_factory=list)
    unaligned: list[ReportSubStep] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
