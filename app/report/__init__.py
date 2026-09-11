"""HTML 测试报告生成入口。

用法（由 runner 调用）：
    from app.report import generate_report
    report_dir = generate_report(results, config.report, model, report_name)

其中 results 是 list[RunResult]（每个 RunResult 含 platform_alias / case / history，
history 为 None 表示该用例未执行，如登录失败）。

流程：建报告目录 → 抢救 screenshots → 对每个结果提取/对齐/判定 →
聚合（按平台分块 + 多用例）→ 截图落盘 → 渲染 → 写文件。返回报告目录路径。
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from .align import align, extract_substeps
from .judge import judge
from .models import (
    CaseBlock,
    PlatformBlock,
    Report,
    ReportMeta,
    ReportStep,
    RunResult,
    StepStatus,
)
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
    """把名称转成安全目录名。"""
    s = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", name or "batch").strip("-")
    return s[:64] or "batch"


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


def _persist_screenshots(history: Any, raw_dir: Path, prefix: str) -> int:
    """抢救 history 里所有 step 的 screenshot 到 raw_dir，并原地改写
    state.screenshot_path 为持久化路径。

    修复 browser-use 0.13.10 的现象：`agent.run()` 返回后，部分 step 的 tmp 截图
    文件在报告生成时已不可读。这里统一复制到 run_dir/_raw/，保证后续
    `state.get_screenshot()` 从持久化路径读到 base64。

    prefix 用于区分不同用例的截图（避免多 history 文件名冲突）。
    """
    raw_dir.mkdir(parents=True, exist_ok=True)
    items = getattr(history, "history", None) or []
    ok = 0
    for i, item in enumerate(items, start=1):
        state = getattr(item, "state", None)
        if state is None:
            continue
        sp = getattr(state, "screenshot_path", None)
        if not sp:
            continue
        try:
            src = Path(sp)
        except (TypeError, ValueError):
            continue
        if not src.exists() or not src.is_file():
            continue
        dst = raw_dir / f"{prefix}{i:04d}.png"
        try:
            shutil.copy(src, dst)
        except OSError:
            continue
        try:
            state.screenshot_path = str(dst)
        except Exception:
            pass
        ok += 1
    return ok


def _build_case_block(r: RunResult) -> CaseBlock:
    """把单个 RunResult 转成 CaseBlock（含提取/对齐/判定）。"""
    case = r.case
    name = getattr(case, "name", "") or ""
    desc = getattr(case, "description", "") or ""

    if r.history is None:
        return CaseBlock(
            name=name,
            description=desc,
            status=StepStatus.SKIPPED,
            final_result=r.note or "",
        )

    substeps = extract_substeps(r.history)
    steps, unaligned = align(substeps, getattr(case, "steps", []) or [])
    judge(steps)

    return CaseBlock(
        name=name,
        description=desc,
        status=_case_status(steps),
        duration=_case_duration(steps),
        final_result=_final_result(r.history),
        steps=steps,
        unaligned=unaligned,
    )


def _merge_usage(results: list[RunResult]) -> dict[str, Any]:
    """合并多个 history 的 token 用量（数值累加，非数值取首次）。"""
    merged: dict[str, Any] = {}
    for r in results:
        if r.history is None:
            continue
        for k, v in _usage_dict(r.history).items():
            if isinstance(v, (int, float)):
                merged[k] = merged.get(k, 0) + v
            else:
                merged.setdefault(k, v)
    return merged


def generate_report(
    results: list[RunResult],
    report_config: Any,
    model: str = "",
    report_name: str = "",
) -> str:
    """把一次运行的多个用例结果聚合为一份 HTML 报告，返回报告目录路径。"""
    now = datetime.now()
    output_dir = Path(getattr(report_config, "output_dir", "./reports") or "./reports")
    first_name = ""
    if results and results[0].case is not None:
        first_name = getattr(results[0].case, "name", "") or ""
    run_dir = output_dir / _slug(report_name or first_name) / now.strftime("%Y%m%d-%H%M%S")
    raw_dir = run_dir / "_raw"
    run_dir.mkdir(parents=True, exist_ok=True)

    # 1) 抢救截图 + 构建用例块（按平台分组）
    platforms_map: dict[str, list[CaseBlock]] = {}
    for idx, r in enumerate(results, start=1):
        if r.history is not None:
            _persist_screenshots(r.history, raw_dir, f"{idx}-")
        alias = r.platform_alias or "default"
        platforms_map.setdefault(alias, []).append(_build_case_block(r))

    platforms = [PlatformBlock(name=k, cases=v) for k, v in platforms_map.items()]

    # 2) 聚合元信息
    total = sum(len(p.cases) for p in platforms)
    passed = sum(1 for p in platforms for c in p.cases if c.status == StepStatus.SUCCESS)
    failed = total - passed
    usage = _merge_usage(results)
    meta = ReportMeta(
        report_id=f"RPT-{now.strftime('%Y%m%d-%H%M%S')}",
        run_time=now.strftime("%Y-%m-%d %H:%M:%S"),
        model=model,
        total_tokens=str(usage.get("total_tokens", 0)),
        browser="Chromium",
        total_cases=total,
        passed=passed,
        failed=failed,
        pass_rate=f"{passed * 100 // total}%" if total else "0%",
    )
    report = Report(meta=meta, platforms=platforms)

    # 3) 截图落盘 + 渲染
    save_screenshots(report, run_dir / "screenshots")
    html = render_html(report, detail=bool(getattr(report_config, "detail", False)))
    (run_dir / "report.html").write_text(html, encoding="utf-8")
    write_token_log(usage, run_dir / "token_usage.log")

    return str(run_dir)
