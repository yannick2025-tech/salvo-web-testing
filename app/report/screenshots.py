"""截图落盘。

把子步骤携带的 base64 截图解码写入报告目录的 screenshots/ 下，并应用
「失败重试只留首次失败 + 最终状态」的保留策略控制截图数量。
"""

from __future__ import annotations

import base64
from pathlib import Path
from typing import Optional

from .models import Report, ReportStep, ReportSubStep


def decode_screenshot(screenshot: str) -> Optional[bytes]:
    """把 base64 截图字符串解码为 PNG 字节；为空/非法返回 None。"""
    if not screenshot:
        return None
    try:
        return base64.b64decode(screenshot)
    except Exception:
        return None


def apply_retention_policy(
    steps: list[ReportStep], unaligned: list[ReportSubStep]
) -> None:
    """标记每个子步骤是否保留截图。

    规则（每个用例步骤内部）：
    - 成功子步骤：全保留。
    - 失败子步骤：仅保留「该步骤第一次失败」或「该步骤最后一个子步骤（最终失败）」
      的截图，中间重复失败截图丢弃。
    - 未归类子步骤：全保留（避免丢信息）。
    """
    for step in steps:
        seen_failure = False
        last = step.substeps[-1] if step.substeps else None
        for ss in step.substeps:
            if ss.success:
                ss.keep_screenshot = True
                seen_failure = False
            else:
                ss.keep_screenshot = (not seen_failure) or (ss is last)
                seen_failure = True
    for ss in unaligned:
        ss.keep_screenshot = True


def _write_png(ss: ReportSubStep, screenshots_dir: Path, filename: str) -> None:
    """解码并写入一张截图，成功后回填相对路径。"""
    data = decode_screenshot(ss.screenshot)
    if data is None:
        return
    (screenshots_dir / filename).write_bytes(data)
    ss.screenshot_path = f"screenshots/{filename}"


def save_screenshots(report: Report, screenshots_dir: Path) -> None:
    """为报告所有用例落盘截图（应用保留策略，命名跨平台/用例唯一）。"""
    screenshots_dir.mkdir(parents=True, exist_ok=True)

    for pi, platform in enumerate(report.platforms, start=1):
        for ci, case in enumerate(platform.cases, start=1):
            apply_retention_policy(case.steps, case.unaligned)
            prefix = f"{pi}-{ci}-"
            for step in case.steps:
                for j, ss in enumerate(step.substeps, start=1):
                    if not ss.keep_screenshot:
                        continue
                    _write_png(ss, screenshots_dir, f"{prefix}{step.index}-{j}.png")
            for ss in case.unaligned:
                _write_png(ss, screenshots_dir, f"{prefix}unaligned-{ss.index}.png")
