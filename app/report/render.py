"""HTML 渲染与 token 日志。

用标准库 html.escape + 内联 CSS 生成单文件 HTML；token 用量写入日志文件。
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from .models import ReportCase, ReportStep, ReportSubStep, StepStatus

_STATUS_LABEL = {
    StepStatus.SUCCESS: ("成功", "#16a34a"),
    StepStatus.FAILED: ("失败", "#dc2626"),
    StepStatus.SKIPPED: ("未执行", "#9ca3af"),
}

_CSS = """
body { font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
       margin: 0; background: #f5f6f8; color: #1f2937; }
header { background: #fff; border-bottom: 1px solid #e5e7eb; padding: 20px 32px; }
h1 { margin: 0 0 6px; font-size: 20px; }
.meta { color: #6b7280; font-size: 13px; }
.result { margin-top: 10px; font-size: 14px; white-space: pre-wrap; }
main { max-width: 1080px; margin: 24px auto; padding: 0 16px 48px; }
section.step { background: #fff; border: 1px solid #e5e7eb; border-radius: 8px;
               margin-bottom: 16px; overflow: hidden; }
.step-head { display: flex; align-items: center; gap: 10px; padding: 12px 16px;
             border-bottom: 1px solid #f0f1f3; }
.step-title { font-weight: 600; }
.badge { color: #fff; font-size: 12px; padding: 2px 10px; border-radius: 999px; }
.substep { padding: 10px 16px; border-bottom: 1px solid #f7f8fa; }
.substep:last-child { border-bottom: none; }
.substep-head { display: flex; align-items: center; gap: 8px; font-size: 14px; }
.dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.substep-action { font-weight: 500; }
.substep-meta { color: #9ca3af; font-size: 12px; }
.substep-error { color: #dc2626; font-size: 13px; margin-top: 4px; }
.substep-detail { color: #4b5563; font-size: 12px; margin-top: 4px;
                  word-break: break-all; }
.shot { max-width: 100%; border: 1px solid #e5e7eb; border-radius: 4px;
        margin-top: 8px; display: block; }
.no-shot { color: #9ca3af; font-size: 12px; margin-top: 4px; }
.unaligned { background: #fffbeb; border-color: #fde68a; }
"""


def _esc(text: Any) -> str:
    return escape(str(text if text is not None else ""))


def _badge(status: StepStatus) -> str:
    label, color = _STATUS_LABEL[status]
    return f'<span class="badge" style="background:{color}">{label}</span>'


def _render_substep(ss: ReportSubStep, detail: bool) -> str:
    color = "#16a34a" if ss.success else "#dc2626"
    parts = [
        '<div class="substep">',
        '<div class="substep-head">',
        f'<span class="dot" style="background:{color}"></span>',
        f'<span class="substep-action">{_esc(ss.action_desc or "无动作")}</span>',
    ]
    if ss.duration is not None:
        parts.append(f'<span class="substep-meta">{ss.duration:.1f}s</span>')
    parts.append("</div>")

    if ss.error:
        parts.append(f'<div class="substep-error">失败原因：{_esc(ss.error)}</div>')

    if detail:
        if ss.thinking:
            parts.append(f'<div class="substep-detail"><b>thinking：</b>{_esc(ss.thinking)}</div>')
        if ss.next_goal:
            parts.append(f'<div class="substep-detail"><b>next_goal：</b>{_esc(ss.next_goal)}</div>')
        if ss.url:
            parts.append(f'<div class="substep-detail"><b>url：</b>{_esc(ss.url)}</div>')
        if ss.title:
            parts.append(f'<div class="substep-detail"><b>title：</b>{_esc(ss.title)}</div>')

    if ss.screenshot_path:
        parts.append(f'<img class="shot" src="{_esc(ss.screenshot_path)}" alt="截图" loading="lazy">')
    else:
        parts.append('<div class="no-shot">无截图</div>')

    parts.append("</div>")
    return "\n".join(parts)


def _render_step(step: ReportStep, detail: bool) -> str:
    parts = [
        '<section class="step">',
        '<div class="step-head">',
        f'<span class="step-title">步骤 {step.index} · {_esc(step.action)} · {_esc(step.target)}</span>',
        _badge(step.status),
        "</div>",
    ]
    if step.substeps:
        for ss in step.substeps:
            parts.append(_render_substep(ss, detail))
    else:
        parts.append('<div class="substep"><span class="no-shot">该步骤未执行</span></div>')
    parts.append("</section>")
    return "\n".join(parts)


def _overall_badge(success: bool | None) -> str:
    if success is True:
        label, color = "通过", "#16a34a"
    elif success is False:
        label, color = "失败", "#dc2626"
    else:
        label, color = "未完成", "#9ca3af"
    return f'<span class="badge" style="background:{color}">{label}</span>'


def _usage_table(usage: dict[str, Any]) -> str:
    if not usage:
        return ""
    rows = []
    for k, v in usage.items():
        if isinstance(v, dict):
            continue
        rows.append(f"<tr><td>{_esc(k)}</td><td>{_esc(v)}</td></tr>")
    if not rows:
        return ""
    return (
        '<h3>Token 用量</h3>'
        '<table style="border-collapse:collapse;font-size:13px">'
        f'{"".join(rows)}'
        "</table>"
    )


def render_html(report: ReportCase, detail: bool = False) -> str:
    """把报告数据渲染成完整 HTML 字符串。"""
    parts = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        f"<title>测试报告 - {_esc(report.name)}</title>",
        f"<style>{_CSS}</style>",
        "</head>",
        "<body>",
        "<header>",
        f"<h1>{_esc(report.name)}</h1>",
        f'<div class="meta">{_esc(report.description)}</div>',
        f'<div class="meta">整体结果：{_overall_badge(report.overall_success)}</div>',
    ]
    if report.final_result:
        parts.append(f'<div class="result">{_esc(report.final_result)}</div>')
    if detail:
        parts.append(_usage_table(report.usage))
    parts.append("</header>")
    parts.append("<main>")

    for step in report.steps:
        parts.append(_render_step(step, detail))

    if report.unaligned:
        parts.append('<section class="step unaligned">')
        parts.append('<div class="step-head"><span class="step-title">未归类步骤</span></div>')
        for ss in report.unaligned:
            parts.append(_render_substep(ss, detail))
        parts.append("</section>")

    parts.append("</main>")
    parts.append("</body>")
    parts.append("</html>")
    return "\n".join(parts)


def write_token_log(usage: dict[str, Any], path: Path) -> None:
    """把 token 用量写入日志文件。"""
    lines: list[str] = []
    for k, v in usage.items():
        if isinstance(v, dict):
            for kk, vv in v.items():
                lines.append(f"{k}.{kk} = {vv}")
        else:
            lines.append(f"{k} = {v}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
