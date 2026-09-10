"""HTML 测试报告生成入口。

用法（由 runner 调用）：
    from app.report import generate_report
    report_dir = generate_report(history, case, report_config)

流程：提取子步骤 → 对齐 → 判定 → 截图落盘 → 渲染 → 写文件。
返回报告目录路径。
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Any

from .align import align, extract_substeps
from .judge import judge
from .models import ReportCase
from .render import render_html, write_token_log
from .screenshots import save_screenshots


def _overall_success(history: Any) -> bool | None:
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


def generate_report(history: Any, case: Any, report_config: Any) -> str:
    """生成一次运行的 HTML 报告，返回报告目录路径。"""
    substeps = extract_substeps(history)
    steps, unaligned = align(substeps, case.steps)
    judge(steps)

    report = ReportCase(
        name=case.name,
        description=getattr(case, "description", "") or "",
        overall_success=_overall_success(history),
        final_result=_final_result(history),
        steps=steps,
        unaligned=unaligned,
        usage=_usage_dict(history),
    )

    output_dir = Path(getattr(report_config, "output_dir", "./reports") or "./reports")
    run_dir = output_dir / _slug(case.name) / datetime.now().strftime("%Y%m%d-%H%M%S")
    screenshots_dir = run_dir / "screenshots"
    run_dir.mkdir(parents=True, exist_ok=True)

    save_screenshots(report, screenshots_dir)

    html = render_html(report, detail=bool(getattr(report_config, "detail", False)))
    (run_dir / "report.html").write_text(html, encoding="utf-8")

    write_token_log(report.usage, run_dir / "token_usage.log")

    return str(run_dir)
