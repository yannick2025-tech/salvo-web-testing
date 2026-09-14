"""命中即自动设值（确定性绕过 LLM 试错）。

背景
----
某些框架控件（Element UI el-date-range-picker 的 el-range-input）无法靠 LLM
用 browser-use 原生 input/click 设值：
- browser-use input 是"追加式打字"，会把已有 datetime 拼成乱码；
- 该控件必须用"原生 value setter + input 事件 + Enter"（input_enter）才生效。

记忆只记录"这是某日期范围控件、需 input_enter"，**不含具体日期**；
具体起止日期由本模块的日期窗口计算器在每次应用时动态生成，故跨天/跨周都正确。

本模块在 Agent 每步 _prepare_context 抓 DOM **之前**执行：先按记忆匹配到
页面上的日期范围控件，若其当前值 != 目标窗口，则用 input_enter 一次设对。
由于设值发生在抓取之前，LLM 当步看到的 DOM 已是正确值 → 不会再尝试该控件。
"""

from __future__ import annotations

import datetime
import fnmatch
import logging
from typing import Any, Optional

from .models import ElementMemoryConfig

logger = logging.getLogger(__name__)


def compute_date_window(cfg: ElementMemoryConfig) -> tuple[str, str]:
    """按配置计算目标日期窗口 [start, end]（yyyy-MM-dd）。

    默认：查"今天往前 N 天 ~ 今天往前 1 天"（不含今天）。
    例 days_back=10, include_today=False，今天 09-06 -> 08-26 ~ 09-05。
    """
    today = datetime.date.today()
    days_back = max(1, int(cfg.date_range_days_back or 10))
    if cfg.date_range_include_today:
        start = today - datetime.timedelta(days=days_back - 1)
        end = today
    else:
        start = today - datetime.timedelta(days=days_back)
        end = today - datetime.timedelta(days=1)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")


def _url_matches(pattern: Optional[str], url: str) -> bool:
    """glob 匹配 URL（* 通配）。无 pattern 视为匹配。"""
    if not pattern:
        return True
    try:
        return fnmatch.fnmatch(url, pattern) or pattern.strip("*") in url
    except Exception:
        return False


def _is_range_date_control(sig) -> bool:
    """判断记忆是否对应"日期范围控件"。

    Element UI 的 daterange 固定使用 `el-range-input` class，且本项目只有 Element UI，
    故只此一条规则即可——任何 `tag=input + 有 class` 的记忆（如账号/密码/下拉输入）
    都不应被纳入 auto_apply，否则会把订单的日期窗口误带入其他场景（站点列表等）。
    """
    if sig is None:
        return False
    classes = " ".join(sig.class_fragments or [])
    return "el-range-input" in classes


# 判断当前 DOM 中该控件是否已是目标窗口的 JS（只读，返回现状）
_CHECK_JS = r"""
(function(){
  try{
    var ins=Array.prototype.slice.call(document.querySelectorAll('input.el-range-input'));
    if(ins.length<2) return {present:false, vals:[]};
    return {present:true, vals:ins.map(function(i){return i.value||'';})};
  }catch(e){ return {present:false, error:String(e)}; }
})();
"""


# 对前两个 el-range-input 依次"清空+输入+回车"的 JS。
# Element UI 的 daterange 需要 input blur 后才会把值写入 pickerRange，
# 最后再主动点击 panel 的"确定"按钮以确保提交（picker.commit）。
def _build_set_js(start: str, end: str) -> str:
    return r"""(function(){
  var ins=Array.prototype.slice.call(document.querySelectorAll('input.el-range-input'));
  function setVal(el, text){
    var proto = el instanceof HTMLInputElement ? HTMLInputElement.prototype : HTMLTextAreaElement.prototype;
    var setter = Object.getOwnPropertyDescriptor(proto,'value').set;
    setter.call(el,''); el.dispatchEvent(new Event('input',{bubbles:true}));
    setter.call(el,text); el.dispatchEvent(new Event('input',{bubbles:true}));
    el.focus();
    el.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',bubbles:true,cancelable:true}));
    el.dispatchEvent(new KeyboardEvent('keyup',{key:'Enter',code:'Enter',bubbles:true}));
    el.dispatchEvent(new Event('change',{bubbles:true}));
    el.blur();
  }
  var n=0;
  if(ins.length>=2){ setVal(ins[0], %s); setVal(ins[1], %s); n=2; }
  else if(ins.length>=1){ setVal(ins[0], %s); n=1; }
  // 主动点击 picker panel 的"确定"按钮，确保 pickerRange 提交到 editor.value。
  // Element UI 2.x 的 daterange panel 底部确定按钮：.el-picker-panel .el-button--primary
  var committed = false;
  try{
    var btn = document.querySelector('.el-picker-panel .el-button--primary');
    if(btn && !btn.disabled){ btn.click(); committed = true; }
  }catch(e){}
  return {set:n, committed: committed};
})();
""" % (f"'{start}'", f"'{end}'", f"'{start}'")


async def _eval(browser_session: Any, expression: str) -> Any:
    """在 agent 焦点页执行 JS。

    Runtime.evaluate 返回 dict：result['result']['value']（见 browser_use 源码）。
    """
    cdp = await browser_session.get_or_create_cdp_session(
        target_id=browser_session.agent_focus_target_id, focus=False
    )
    result = await cdp.cdp_client.send.Runtime.evaluate(
        params={"expression": expression, "returnByValue": True},
        session_id=cdp.session_id,
    )
    if isinstance(result, dict):
        return result.get("result", {}).get("value")
    try:
        return result.result.value
    except Exception:
        return None


async def auto_apply_date_ranges(
    browser_session: Any,
    store,
    cfg: ElementMemoryConfig,
) -> Optional[str]:
    """扫描记忆中的日期范围控件，命中且当前值!=目标窗口则自动设值。

    返回描述做了什么，供日志。无控件/无需设值返回 None。
    """
    if not cfg.auto_apply_enabled:
        return None
    if browser_session is None:
        return None

    memories = list(store.get_all())
    if not memories:
        return None

    try:
        # 1) 当前 URL
        url_info = await _eval(browser_session, "location.href")
        current_url = str(url_info) if url_info else ""
        # 2) 只取"日期范围控件"记忆，且其 url_pattern 与当前页匹配
        controls = [
            m
            for m in memories
            if _is_range_date_control(m.element_signature)
            and _url_matches(m.context.url_pattern, current_url)
        ]
        if not controls:
            logger.debug(f"[auto_apply] 无命中控件记忆 (url={current_url}, 记忆数={len(memories)})")
            return None

        # 3) 检查当前 DOM 是否存在 el-range-input
        state = await _eval(browser_session, _CHECK_JS)
        if not (isinstance(state, dict) and state.get("present")):
            logger.debug(f"[auto_apply] DOM 无 el-range-input: {state}")
            return None

        start, end = compute_date_window(cfg)

        # 只在前两框当前值不是目标时才设（幂等）
        vals = state.get("vals", []) or []
        already = False
        if len(vals) >= 2:
            already = vals[0].startswith(start) and vals[1].startswith(end)
        if already:
            logger.debug(f"[auto_apply] 已是目标窗口 {start}~{end}，跳过: {vals}")
            return None

        logger.info(f"[auto_apply] 当前值 {vals} -> 设为目标 {start} ~ {end}")
        await _eval(browser_session, _build_set_js(start, end))
        # 设值可能异步生效，简单等待
        import asyncio

        await asyncio.sleep(0.2)
        return f"{start} ~ {end}"
    except Exception as e:
        logger.debug(f"[auto_apply] 执行异常(不影响主流程): {e}", exc_info=True)
        return None
