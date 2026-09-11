"""用例步骤三态判定（final-state-wins）。"""

from __future__ import annotations

from .align import is_aux_substep
from .models import ReportStep, StepStatus


def judge(steps: list[ReportStep]) -> None:
    """原地判定每个用例步骤的状态。

    规则：以最终状态为准——
    - 无子步骤 -> 未执行（灰）
    - 最后一个**主动作**子步骤成功 -> 成功（绿），即使中间或后面的辅助动作
      （scroll/wait 等）有失败
    - 最后一个主动作子步骤失败 -> 失败（红）
    - 全是辅助动作时，退化为看最后一个子步骤

    跳过辅助动作（scroll / wait / 读文件等）是为了避免它们的失败误判
    用例步骤的真实结果。
    """
    for step in steps:
        if not step.substeps:
            step.status = StepStatus.SKIPPED
            continue
        main = None
        for ss in reversed(step.substeps):
            if not is_aux_substep(ss):
                main = ss
                break
        if main is None:
            main = step.substeps[-1]
        step.status = StepStatus.SUCCESS if main.success else StepStatus.FAILED
