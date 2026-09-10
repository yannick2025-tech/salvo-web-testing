"""截图落盘与保留策略单元测试。"""

import base64

from app.report.models import CaseBlock, PlatformBlock, Report, ReportStep, ReportSubStep
from app.report.screenshots import (
    apply_retention_policy,
    decode_screenshot,
    save_screenshots,
)


def _ss(success, screenshot="aGVsbG8="):
    return ReportSubStep(index=1, action_names=["click"], success=success, screenshot=screenshot)


def test_decode_screenshot_valid():
    assert decode_screenshot(base64.b64encode(b"png").decode()) == b"png"


def test_decode_screenshot_empty_or_invalid():
    assert decode_screenshot("") is None
    assert decode_screenshot(None) is None
    assert decode_screenshot("!!!not-base64!!!") is None


def test_retention_policy_keeps_first_fail_and_final_success():
    step = ReportStep(
        index=1,
        action="click",
        target="x",
        substeps=[_ss(True), _ss(False), _ss(False), _ss(False), _ss(True)],
    )
    apply_retention_policy([step], [])
    kept = [ss.keep_screenshot for ss in step.substeps]
    assert kept == [True, True, False, False, True]


def test_retention_policy_keeps_final_failure():
    step = ReportStep(
        index=1,
        action="click",
        target="x",
        substeps=[_ss(True), _ss(False), _ss(False)],
    )
    apply_retention_policy([step], [])
    kept = [ss.keep_screenshot for ss in step.substeps]
    # 成功保留；第一个失败保留；最终失败（最后一个子步骤）保留
    assert kept == [True, True, True]


def test_retention_policy_unaligned_all_kept():
    unaligned = [_ss(False), _ss(False)]
    apply_retention_policy([], unaligned)
    assert all(ss.keep_screenshot for ss in unaligned)


def test_save_screenshots_writes_files(tmp_path):
    report = Report(
        platforms=[
            PlatformBlock(
                name="manhattan",
                cases=[
                    CaseBlock(
                        name="t",
                        steps=[
                            ReportStep(
                                index=1,
                                action="click",
                                target="x",
                                substeps=[_ss(True), _ss(False)],
                            )
                        ],
                        unaligned=[_ss(False, screenshot=base64.b64encode(b"u").decode())],
                    )
                ],
            )
        ]
    )
    screenshots_dir = tmp_path / "screenshots"
    save_screenshots(report, screenshots_dir)

    assert (screenshots_dir / "1-1-1-1.png").exists()
    assert (screenshots_dir / "1-1-1-2.png").exists()
    assert (screenshots_dir / "1-1-unaligned-1.png").exists()
    assert report.platforms[0].cases[0].steps[0].substeps[0].screenshot_path == "screenshots/1-1-1-1.png"
