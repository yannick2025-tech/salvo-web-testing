"""HTML 测试报告生成入口。

用法（由 runner 调用）：
    from app.report import generate_report
    report_dir = generate_report(history, case, config.report, platform_alias, model)

流程：提取子步骤 → 对齐 → 判定 → 组装报告结构（meta + 平台 + 用例）→
截图落盘 → 渲染 → 写文件。返回报告目录路径。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .align import align, extract_substeps
from .judge import judge
from .models import CaseBlock, PlatformBlock, Report, ReportMeta, ReportStep, StepStatus
from .render import render_html, write_token_log
from .screenshots import save_screenshots


def _overall_success(history: Any) -> Optional[bool]:
    fn = getattr(history, "is_successful", None)
    if callable(fn):
        try:
            return fn()
        except Exception:
            return None
    return None


def _final_result(history: Any) -> str:
    fn = getattr(history, "final_result", None)
    if callable(fn):
        try:
            return fn() or ""
        except Exception:
            return ""
    return ""


def _usage_dict(history: Any) -> dict[str, Any]:
    usage = getattr(history, "usage", None)
    if usage is None:
        return {}
    data = usage.model_dump() if hasattr(usage, "model_dump") else usage
    if isinstance(data, dict):
        return data
    return dict(vars(usage)) if hasattr(usage, "__dict__") else {}


def _slug(name: str) -> str:
    """把用例名转成安全目录名。"""
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", name or "case").strip("-")
    return s[:64] or "case"


def _case_status(steps: list[ReportStep]) -> StepStatus:
    """用例级状态：任一用例步骤失败则失败，否则成功。"""
    if any(step.status == StepStatus.FAILED for step in steps):
        return StepStatus.FAILED
    return StepStatus.SUCCESS


def _case_duration(steps: list[ReportStep]) -> Optional[float]:
    """汇总所有子步骤耗时（秒）。"""
    total = 0.0
    has = False
    for step in steps:
        for ss in step.substeps:
            if ss.duration is not None:
                total += ss.duration
                has = True
    return total if has else None


def generate_report(
    history: Any,
    case: Any,
    report_config: Any,
    platform_alias: str = "",
    model: str = "",
) -> str:
    """生成一次运行的 HTML 报告，返回报告目录路径。"""
    substeps = extract_substeps(history)
    steps, unaligned = align(substeps, case.steps)
    judge(steps)

    case_block = CaseBlock(
        name=case.name,
        description=getattr(case, "description", "") or "",
        status=_case_status(steps),
        duration=_case_duration(steps),
        final_result=_final_result(history),
        steps=steps,
        unaligned=unaligned,
    )

    platform = PlatformBlock(name=platform_alias or "default", cases=[case_block])

    usage = _usage_dict(history)
    now = datetime.now()
    total_cases = 1
    passed = 1 if case_block.status == StepStatus.SUCCESS else 0
    failed = 1 if case_block.status == StepStatus.FAILED else 0
    meta = ReportMeta(
        report_id=f"RPT-{now.strftime('%Y%m%d-%H%M%S')}",
        run_time=now.strftime("%Y-%m-%d %H:%M:%S"),
        model=model,
        total_tokens=str(usage.get("total_tokens", 0)),
        browser="Chromium",
        total_cases=total_cases,
        passed=passed,
        failed=failed,
        pass_rate=f"{passed * 100 // total_cases}%",
    )

    report = Report(meta=meta, platforms=[platform])

    output_dir = Path(getattr(report_config, "output_dir", "./reports") or "./reports")
    run_dir = output_dir / _slug(case.name) / now.strftime("%Y%m%d-%H%M%S")
    screenshots_dir = run_dir / "screenshots"
    run_dir.mkdir(parents=True, exist_ok=True)

    save_screenshots(report, screenshots_dir)

    html = render_html(report, detail=bool(getattr(report_config, "detail", False)))
    (run_dir / "report.html").write_text(html, encoding="utf-8")

    write_token_log(usage, run_dir / "token_usage.log")

    return str(run_dir)
