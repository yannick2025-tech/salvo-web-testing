"""判定模块单元测试（final-state-wins）。"""

from app.report.judge import judge
from app.report.models import ReportStep, ReportSubStep, StepStatus


def _step(substeps):
    return ReportStep(index=1, action="click", target="x", substeps=substeps)


def _ss(success):
    return ReportSubStep(index=1, action_names=["click_element"], success=success)


def test_success_even_with_internal_failures():
    # 失败 4 次第 5 次成功 → 成功
    step = _step([_ss(True), _ss(False), _ss(False), _ss(False), _ss(False), _ss(True)])
    judge([step])
    assert step.status == StepStatus.SUCCESS


def test_final_failure_is_failed():
    step = _step([_ss(True), _ss(False), _ss(False)])
    judge([step])
    assert step.status == StepStatus.FAILED


def test_no_substeps_is_skipped():
    step = _step([])
    judge([step])
    assert step.status == StepStatus.SKIPPED
