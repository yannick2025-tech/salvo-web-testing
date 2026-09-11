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


def test_judge_ignores_aux_failure():
    """辅助动作（scroll/wait 等）失败不应让用例步骤失败。"""
    step = _step(
        [
            ReportSubStep(index=1, action_names=["click_element"], success=True),
            ReportSubStep(index=2, action_names=["scroll"], success=False),  # 辅助失败
        ]
    )
    judge([step])
    assert step.status == StepStatus.SUCCESS  # judge 跳过 scroll 失败


def test_judge_uses_last_main_action_when_trailing_aux_fails():
    """末尾是辅助动作且失败时，取最后一个主动作的 success 判定。"""
    step = _step(
        [
            ReportSubStep(index=1, action_names=["click_element"], success=True),
            ReportSubStep(index=2, action_names=["wait"], success=False),
        ]
    )
    judge([step])
    assert step.status == StepStatus.SUCCESS


def test_judge_main_action_failure_is_failed():
    """主操作失败即使末尾跟辅助成功，仍判失败。"""
    step = _step(
        [
            ReportSubStep(index=1, action_names=["click_element"], success=False),
            ReportSubStep(index=2, action_names=["scroll"], success=True),
        ]
    )
    judge([step])
    assert step.status == StepStatus.FAILED
