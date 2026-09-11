"""HTML 渲染与 token 日志。

视觉方向：C · Editorial（编辑科技）——衬线大标题 + 细线分隔 + 大数字横排，
克制、杂志感。字体用系统栈保证离线可用。用标准库 html.escape + 内联 CSS 生成单文件 HTML。
"""

from __future__ import annotations

from html import escape
from pathlib import Path
from typing import Any

from .models import (
    CaseBlock,
    PlatformBlock,
    Report,
    ReportMeta,
    ReportStep,
    ReportSubStep,
    StepStatus,
)

_STATUS_LABEL = {
    StepStatus.SUCCESS: ("通过", "#0f8a4d"),
    StepStatus.FAILED: ("失败", "#d22730"),
    StepStatus.SKIPPED: ("未执行", "#a8a093"),
}

_CSS = """
:root { --bg:#fbfaf7; --panel:#fffdfa; --text:#141414; --muted:#8a857a;
  --line:#e6e1d6; --accent:#0a5cff; --pass:#0f8a4d; --fail:#d22730; --skip:#a8a093; }
* { box-sizing:border-box; margin:0; padding:0; }
body { background:var(--bg); color:var(--text); font-family:-apple-system,BlinkMacSystemFont,"PingFang SC","Hiragino Sans GB","Microsoft YaHei","微软雅黑","Source Han Sans SC","Noto Sans CJK SC",sans-serif;
  padding-bottom:72px; }
.serif { font-family:Georgia,"Songti SC","STSongti-SC-Regular","Hiragino Mincho ProN","Source Han Serif SC","Noto Serif CJK SC","STSong","SimSun","宋体",serif; }
.wrap { max-width:1200px; margin:0 auto; padding:0 32px; }

.top { padding:56px 0 0; border-bottom:2px solid var(--text); }
.kicker { font-size:12px; font-weight:700; letter-spacing:.2em; text-transform:uppercase; color:var(--accent); }
h1 { font-family:Georgia,"Songti SC","Noto Serif SC",serif; font-size:44px; font-weight:600;
  letter-spacing:-.01em; margin-top:10px; line-height:1.1; }
.sub { color:var(--muted); font-size:13px; margin-top:12px; padding-bottom:20px; }

.stats { display:grid; grid-template-columns:repeat(4,1fr); margin-top:28px; }
.stat { padding:4px 28px; border-left:1px solid var(--line); }
.stat:first-child { border-left:none; padding-left:0; }
.stat .lab { font-size:11px; font-weight:700; letter-spacing:.14em; text-transform:uppercase; color:var(--muted); }
.stat .val { font-family:Georgia,"Songti SC","Noto Serif SC",serif; font-size:46px; font-weight:600;
  line-height:1.1; margin-top:6px; font-variant-numeric:tabular-nums; }
.stat.good .val { color:var(--pass); }
.stat.bad .val { color:var(--fail); }

.metainfo { display:flex; flex-wrap:wrap; gap:10px 40px; margin-top:26px; padding:0 0 20px;
  border-bottom:1px solid var(--line); }
.metainfo .it { font-size:13px; display:flex; gap:10px; align-items:baseline; }
.metainfo b { font-size:11px; font-weight:700; letter-spacing:.1em; text-transform:uppercase; color:var(--muted); }
.metainfo span { font-weight:600; font-variant-numeric:tabular-nums; }

.platform { margin-top:36px; }
.ph { display:flex; align-items:baseline; gap:14px; margin-bottom:16px; }
.ph h2 { font-family:Georgia,"Songti SC","Noto Serif SC",serif; font-size:24px; font-weight:600; }
.ph .cnt { font-size:12px; color:var(--muted); }
.cases { display:flex; flex-direction:column; }
.case { border-top:1px solid var(--line); }
.case:last-child { border-bottom:1px solid var(--line); }
.case-head { display:flex; align-items:center; gap:16px; padding:20px 4px; border:none;
  background:none; text-align:left; font-size:16px; color:var(--text); width:100%; cursor:pointer; }
.badge { font-size:11px; font-weight:700; letter-spacing:.06em; text-transform:uppercase; padding:2px 0; }
.badge.pass { color:var(--pass); }
.badge.fail { color:var(--fail); }
.badge.skip { color:var(--skip); }
.cname { font-family:Georgia,"Songti SC","Noto Serif SC",serif; font-size:19px; font-weight:600; flex:1; }
.cmeta { color:var(--muted); font-size:12.5px; font-variant-numeric:tabular-nums; }
.chev { width:18px; height:18px; color:var(--muted); transition:transform .25s; flex:none; }
.case.open .chev { transform:rotate(90deg); }
.case-body { max-height:0; overflow:hidden; transition:max-height .4s cubic-bezier(.4,0,.2,1); }
.case.open .case-body { max-height:9000px; }
.cb-in { padding:0 4px 24px; }

.step { margin-bottom:2px; border:1px solid var(--line); }
.step-head { display:flex; align-items:center; gap:12px; padding:12px 18px; font-size:13.5px; background:var(--bg); }
.idx { font-weight:700; color:var(--muted); font-size:12px; }
.stitle { font-weight:600; flex:1; }
.dot { width:8px; height:8px; border-radius:50%; flex:none; }
.dot.pass { background:var(--pass); }
.dot.fail { background:var(--fail); }
.dot.skip { background:var(--skip); }
.substeps { padding:6px 18px 14px; }
.substep { display:flex; gap:18px; padding:11px 0; border-top:1px solid var(--line); }
.substep:first-child { border-top:none; }
.info { flex:1; font-size:13px; line-height:1.6; min-width:0; }
.act { font-weight:600; }
.m2 { color:var(--muted); font-size:12px; margin-top:2px; word-break:break-all; }
.err { color:var(--fail); font-size:12px; margin-top:4px; }
.shot { width:200px; height:112px; flex:none; object-fit:cover; background:#1c1c1c; border:none; }
.no-shot { width:200px; height:112px; flex:none; display:flex; align-items:center; justify-content:center;
  font-size:12px; color:var(--muted); background:#f0ede4; }
.unaligned { border-color:#d8d0c2; }
.ual-head { color:var(--muted); font-size:13px; font-weight:600; padding:12px 4px; }
"""


def _esc(text: Any) -> str:
    return escape(str(text if text is not None else ""))


def _badge(status: StepStatus) -> str:
    label, _ = _STATUS_LABEL[status]
    return f'<span class="badge {status.value}">{label}</span>'


def _dot(status: StepStatus) -> str:
    return f'<span class="dot {status.value}"></span>'


def _render_substep(ss: ReportSubStep, detail: bool) -> str:
    parts = ['<div class="substep">']
    act = ss.action_desc or "无动作"
    line = f'<span class="act">{_esc(act)}</span>'
    if ss.duration is not None:
        line += f' · {ss.duration:.1f}s'
    parts.append(f'<div class="info">{line}')

    if ss.error:
        parts.append(f'<div class="err">失败原因：{_esc(ss.error)}</div>')
    if detail:
        if ss.thinking:
            parts.append(f'<div class="m2"><b>thinking：</b>{_esc(ss.thinking)}</div>')
        if ss.next_goal:
            parts.append(f'<div class="m2"><b>next_goal：</b>{_esc(ss.next_goal)}</div>')
        if ss.url:
            parts.append(f'<div class="m2"><b>url：</b>{_esc(ss.url)}</div>')
        if ss.title:
            parts.append(f'<div class="m2"><b>title：</b>{_esc(ss.title)}</div>')

    parts.append("</div>")

    if ss.screenshot_path:
        parts.append(f'<img class="shot" src="{_esc(ss.screenshot_path)}" alt="截图" loading="lazy">')
    else:
        parts.append('<div class="no-shot">无截图</div>')

    parts.append("</div>")
    return "\n".join(parts)


def _render_step(step: ReportStep, detail: bool) -> str:
    parts = [
        '<div class="step">',
        '<div class="step-head">',
        f'<span class="idx">#{step.index:02d}</span>',
        f'<span class="stitle">{_esc(step.action)} · {_esc(step.target)}</span>',
        _dot(step.status),
        "</div>",
        '<div class="substeps">',
    ]
    if step.substeps:
        for ss in step.substeps:
            parts.append(_render_substep(ss, detail))
    else:
        parts.append('<div class="substep"><div class="info" style="color:var(--muted)">该步骤未执行</div></div>')
    parts.append("</div></div>")
    return "\n".join(parts)


def _render_case(case: CaseBlock, detail: bool, idx: int) -> str:
    parts = [
        '<article class="case">',
        '<button class="case-head" aria-expanded="false">',
        _badge(case.status),
        f'<span class="cname">{_esc(case.name)}</span>',
    ]
    meta = []
    if case.duration is not None:
        meta.append(f"{case.duration:.0f}s")
    meta.append(f"{len(case.steps)} 步")
    parts.append(f'<span class="cmeta">{" · ".join(meta)}</span>')
    parts.append(
        '<svg class="chev" viewBox="0 0 20 20" fill="none">'
        '<path d="M7 5l5 5-5 5" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>'
        "</svg>"
    )
    parts.append("</button>")
    parts.append('<div class="case-body"><div class="cb-in">')

    if case.final_result:
        parts.append(f'<div class="m2" style="padding:8px 0 4px">{_esc(case.final_result)}</div>')

    for step in case.steps:
        parts.append(_render_step(step, detail))

    if case.unaligned:
        parts.append('<div class="ual-head">未归类步骤</div>')
        for ss in case.unaligned:
            parts.append(f'<div class="step unaligned">{_render_substep(ss, detail)}</div>')

    parts.append("</div></div></article>")
    return "\n".join(parts)


def _render_platform(platform: PlatformBlock, detail: bool) -> str:
    parts = [
        '<section class="platform">',
        '<div class="ph">',
        f"<h2>{_esc(platform.name or 'default')}</h2>",
        f'<span class="cnt">{len(platform.cases)} 个用例</span>',
        "</div>",
        '<div class="cases">',
    ]
    for idx, case in enumerate(platform.cases, start=1):
        parts.append(_render_case(case, detail, idx))
    parts.append("</div></section>")
    return "\n".join(parts)


def _render_meta(meta: ReportMeta) -> str:
    stats = [
        ("总用例", str(meta.total_cases), ""),
        ("成功", str(meta.passed), "good"),
        ("失败", str(meta.failed), "bad"),
        ("通过率", meta.pass_rate, ""),
    ]
    stat_html = []
    for lab, val, cls in stats:
        cls_attr = f' class="{cls}"' if cls else ""
        stat_html.append(
            f'<div class="stat{cls_attr}"><div class="lab">{lab}</div>'
            f'<div class="val">{_esc(val)}</div></div>'
        )

    metainfo = [
        ("运行时间", meta.run_time),
        ("模型", meta.model),
        ("总 token", meta.total_tokens),
        ("浏览器", meta.browser),
    ]
    meta_html = []
    for lab, val in metainfo:
        meta_html.append(f'<div class="it"><b>{lab}</b><span>{_esc(val)}</span></div>')

    return (
        '<div class="stats">' + "".join(stat_html) + "</div>"
        '<div class="metainfo">' + "".join(meta_html) + "</div>"
    )


def render_html(report: Report, detail: bool = False) -> str:
    """把报告数据渲染成完整 HTML 字符串。"""
    parts = [
        "<!DOCTYPE html>",
        '<html lang="zh-CN">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>Web UI 测试报告</title>",
        f"<style>{_CSS}</style>",
        "</head>",
        "<body>",
        '<div class="wrap">',
        '<div class="top">',
        '<div class="kicker">Test Report</div>',
        '<h1 class="serif">Web UI 测试报告</h1>',
        f'<div class="sub">报告 ID {_esc(report.meta.report_id)} · 由 py-web-testing 自动生成</div>',
        "</div>",
        _render_meta(report.meta),
    ]

    for platform in report.platforms:
        parts.append(_render_platform(platform, detail))

    parts.append("</div>")
    parts.append(
        "<script>"
        "document.querySelectorAll('.case-head').forEach(function(h){"
        "h.addEventListener('click',function(){var c=h.parentElement;"
        "var o=c.classList.toggle('open');h.setAttribute('aria-expanded',o);});});"
        "</script>"
    )
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
