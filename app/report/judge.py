"""用例步骤三态判定（final-state-wins）。"""

from __future__ import annotations

from .models import ReportStep, StepStatus


def judge(steps: list[ReportStep]) -> None:
    """原地判定每个用例步骤的状态。

    规则：以最终状态为准——
    - 无子步骤 -> 未执行（灰）
    - 最后一个子步骤成功 -> 成功（绿），即使中间有失败重试
    - 最后一个子步骤失败 -> 失败（红）
    """
    for step in steps:
        if not step.substeps:
            step.status = StepStatus.SKIPPED
            continue
        last = step.substeps[-1]
        step.status = StepStatus.SUCCESS if last.success else StepStatus.FAILED
