"""Prompt 构成计量器（纯观测）。

量化每次 LLM 调用的 prompt 六部分（系统提示 / 工具定义 / 任务+状态 / 历史 /
浏览器状态(DOM) / 上下文注入）的字符数与估算 token，运行结束输出汇总报告，
用于定位「token 花在哪」并为后续 prompt 裁剪提供基线。

实现方式：全部 monkey-patch `MessageManager.create_state_messages` 与
`get_messages`，不修改 .venv 内的 browser-use 源码；所有 hook 用 try/except
保护，任何异常都不影响主流程。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# token 估算：字符数 ÷ 4（browser-use 内部 MessageCompactionSettings.chars_per_token 同为 4.0）
_CHARS_PER_TOKEN = 4.0

# 六部分列名（与 spec 一致）
_COLUMNS = ("system", "tools", "task+state", "history", "browser_state(DOM)", "context")

_BLOCK_RE_CACHE: dict[str, re.Pattern] = {}


def _block_pattern(tag: str) -> re.Pattern:
    p = _BLOCK_RE_CACHE.get(tag)
    if p is None:
        p = re.compile(rf"<{tag}>\n?(.*?)\n?</{tag}>", re.DOTALL)
        _BLOCK_RE_CACHE[tag] = p
    return p


def extract_block(text: str, tag: str) -> str:
    """从 state message 文本中提取 ``<tag>...</tag>`` 块（无则返回空串）。"""
    m = _block_pattern(tag).search(text)
    return m.group(1) if m else ""


def extract_dom_body(text: str) -> str:
    """提取 browser_state 块内 ``Interactive elements...:`` 之后的 DOM 主体。"""
    bs = extract_block(text, "browser_state")
    m = re.search(r"Interactive elements[^:]*:\n(.*)", bs, re.DOTALL)
    return m.group(1) if m else ""


def _text_len(content: Any) -> int:
    """取消息 content 的文本长度；非纯文本（如多模态 list）返回 0。"""
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        total = 0
        for part in content:
            if isinstance(part, dict):
                total += len(str(part.get("text", "")))
            else:
                total += len(getattr(part, "text", "") or "")
        return total
    return 0


def est_tokens(chars: int) -> int:
    """字符数 → 估算 token（÷ 4，取整）。"""
    return int(chars / _CHARS_PER_TOKEN)


class PromptUsageProfiler:
    """量化每次 LLM 调用 prompt 各部分占比。"""

    def __init__(self) -> None:
        self.system_chars = 0
        self.tools_chars = 0
        self.steps: list[dict[str, int]] = []

    def attach(self, agent: Any) -> None:
        """挂载到 Agent：测固定开销 + patch message manager。"""
        mm = getattr(agent, "_message_manager", None)
        if mm is None:
            logger.debug("[profiler] _message_manager 不存在，跳过挂载")
            return

        self._measure_fixed(agent, mm)

        orig_create = mm.create_state_messages

        def patched_create(*args: Any, **kwargs: Any) -> None:
            try:
                orig_create(*args, **kwargs)
            finally:
                try:
                    self._record_state(mm)
                except Exception as e:  # noqa: BLE001 —— 纯观测，绝不抛出
                    logger.debug(f"[profiler] 记录 state 失败: {e}")

        mm.create_state_messages = patched_create

        orig_get = mm.get_messages

        def patched_get() -> list:
            msgs = orig_get()
            try:
                self._record_context(mm)
            except Exception as e:  # noqa: BLE001
                logger.debug(f"[profiler] 记录 context 失败: {e}")
            return msgs

        mm.get_messages = patched_get
        logger.info("[profiler] 已挂载 prompt 计量")

    # ---- 固定开销 ----

    def _measure_fixed(self, agent: Any, mm: Any) -> None:
        try:
            sm = mm.state.history.system_message
            if sm is not None:
                self.system_chars = _text_len(sm.content)
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[profiler] 测量系统提示失败: {e}")

        try:
            am = getattr(agent, "ActionModel", None)
            if am is not None and hasattr(am, "model_json_schema"):
                schema = am.model_json_schema()
                self.tools_chars = len(json.dumps(schema, ensure_ascii=False))
        except Exception as e:  # noqa: BLE001
            logger.debug(f"[profiler] 测量工具定义失败: {e}")

    # ---- 每步动态部分 ----

    def _record_state(self, mm: Any) -> None:
        text = mm.last_state_message_text or ""
        if not isinstance(text, str) or not text:
            self.steps.append(
                {c: 0 for c in _COLUMNS}
            )
            return
        task_state = len(extract_block(text, "user_request")) + len(extract_block(text, "agent_state"))
        history = len(extract_block(text, "agent_history"))
        browser_state = len(extract_block(text, "browser_state"))
        self.steps.append(
            {
                "system": 0,
                "tools": 0,
                "task+state": task_state,
                "history": history,
                "browser_state(DOM)": browser_state,
                "context": 0,
                "_dom_body": len(extract_dom_body(text)),
            }
        )

    def _record_context(self, mm: Any) -> None:
        if not self.steps:
            return
        total = 0
        try:
            for m in mm.state.history.context_messages or []:
                total += _text_len(m.content)
        except Exception:  # noqa: BLE001
            pass
        self.steps[-1]["context"] = total

    # ---- 报告 ----

    def report(self) -> str:
        """输出汇总报告 + 每步动态部分明细。"""
        if not self.steps:
            return "(无计量数据)"

        sums = {
            "system": self.system_chars,
            "tools": self.tools_chars,
            "task+state": sum(s["task+state"] for s in self.steps),
            "history": sum(s["history"] for s in self.steps),
            "browser_state(DOM)": sum(s["browser_state(DOM)"] for s in self.steps),
            "context": sum(s["context"] for s in self.steps),
        }
        dom_body = sum(s.get("_dom_body", 0) for s in self.steps)
        total_chars = sum(sums.values())

        lines = ["", "===== Prompt Usage Profile ====="]
        header = "  {:<20} {:>12} {:>12} {:>8}".format("part", "chars", "est_tokens", "pct")
        lines.append(header)
        for col in _COLUMNS:
            c = sums[col]
            pct = (c / total_chars * 100) if total_chars else 0.0
            lines.append(
                "  {:<20} {:>12,} {:>12,} {:>7.1f}%".format(col, c, est_tokens(c), pct)
            )
        lines.append(
            "  {:<20} {:>12,} {:>12,} {:>7.1f}%".format("TOTAL", total_chars, est_tokens(total_chars), 100.0)
        )
        if dom_body:
            lines.append(
                "  {:<20} {:>12,}   (其中 DOM 主体 Interactive elements)".format("", dom_body)
            )
        lines.append("  (est_tokens = chars / {})".format(_CHARS_PER_TOKEN))

        # 每步动态部分明细（system/tools 为固定开销，不逐步重复）
        lines.append("")
        lines.append("  ---- per-step 动态部分 (chars) ----")
        lines.append("  {:<5} {:>10} {:>10} {:>10} {:>10}".format("step", "task+state", "history", "browser", "context"))
        for i, s in enumerate(self.steps, start=1):
            lines.append(
                "  {:<5} {:>10,} {:>10,} {:>10,} {:>10,}".format(
                    i, s["task+state"], s["history"], s["browser_state(DOM)"], s["context"]
                )
            )
        lines.append("")
        return "\n".join(lines)
