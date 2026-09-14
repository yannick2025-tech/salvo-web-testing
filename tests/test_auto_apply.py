"""auto_apply 日期范围自动设值的单元测试（无需浏览器，纯逻辑验证）。

覆盖：
1. `_is_range_date_control`：只有 el-range-input 才判为日期范围控件（回归：
   曾因 `tag=input + 有 class` 的宽松规则，把站点列表的"所有"下拉、账号/密码
   等误纳为日期范围控件，导致订单日期窗口被带入站点列表的"开业日期"）。
2. `compute_date_window`：日期窗口计算（过去 N 天，含/不含今天）。
3. `auto_apply_date_ranges`：用例未声明日期目标（target_window=None）时早退不干预。
4. `extract_date_target`：从步骤提取日期范围目标（固定区间 / 相对窗口 / 无声明）。
"""

from __future__ import annotations

import asyncio
from datetime import date, timedelta

from app.case_loader import Step
from app.task_builder import extract_date_target
from browser_use_ext.memory.auto_apply import (
    _is_range_date_control,
    auto_apply_date_ranges,
    compute_date_window,
)
from browser_use_ext.memory.models import ElementMemoryConfig, ElementSignature


def test_is_range_date_control_only_el_range_input():
    """回归：仅 el-range-input 判为日期范围控件，其余 input 均排除。"""
    # 应命中：Element UI 日期范围控件（开始时间）
    assert _is_range_date_control(
        ElementSignature(tag="input", class_fragments=["el-range-input"])
    ) is True

    # 应排除：账号/密码（el-input__inner）
    assert _is_range_date_control(
        ElementSignature(tag="input", class_fragments=["el-input__inner"])
    ) is False

    # 应排除：下拉输入（el-select__input，如"单据时间"）
    assert _is_range_date_control(
        ElementSignature(tag="input", class_fragments=["el-select__input"])
    ) is False

    # 应排除：站点列表的"所有"下拉（el-input__inner + placeholder）
    assert _is_range_date_control(
        ElementSignature(
            tag="input",
            class_fragments=["el-input__inner"],
            attributes={"placeholder": "所有"},
        )
    ) is False

    # 应排除：非 input 元素（button）
    assert _is_range_date_control(
        ElementSignature(tag="button", class_fragments=["el-button"])
    ) is False

    # 应排除：None
    assert _is_range_date_control(None) is False


def test_compute_date_window_exclude_today():
    """过去 10 天（不含今天）：今天 09-14 -> 09-04 ~ 09-13。"""
    cfg = ElementMemoryConfig(date_range_days_back=10, date_range_include_today=False)
    start, end = compute_date_window(cfg)
    today = date.today()
    assert start == (today - timedelta(days=10)).strftime("%Y-%m-%d")
    assert end == (today - timedelta(days=1)).strftime("%Y-%m-%d")


def test_compute_date_window_include_today():
    """过去 10 天（含今天）：今天 09-14 -> 09-05 ~ 09-14。"""
    cfg = ElementMemoryConfig(date_range_days_back=10, date_range_include_today=True)
    start, end = compute_date_window(cfg)
    today = date.today()
    assert start == (today - timedelta(days=9)).strftime("%Y-%m-%d")
    assert end == today.strftime("%Y-%m-%d")


def test_auto_apply_skips_when_no_target_window():
    """用例未声明日期目标（target_window=None）时，auto_apply 早退不干预。"""
    cfg = ElementMemoryConfig(auto_apply_enabled=True)

    class _DummyStore:
        def get_all(self):
            return []

    result = asyncio.run(
        auto_apply_date_ranges(object(), _DummyStore(), cfg, target_window=None)
    )
    assert result is None


def test_extract_date_target_fixed():
    """固定区间：set_date_range 的 start/end 原样返回。"""
    steps = [
        Step(
            action="set_date_range",
            target="日期范围",
            params={"start": "2026-08-01 00:00:00", "end": "2026-08-31 23:59:59"},
        )
    ]
    assert extract_date_target(steps) == ("2026-08-01 00:00:00", "2026-08-31 23:59:59")


def test_extract_date_target_relative():
    """相对窗口：days_back=10 / include_today=False 复用 compute_date_window 规则。"""
    steps = [
        Step(
            action="set_date_range",
            target="日期范围",
            params={"days_back": 10, "include_today": False},
        )
    ]
    start, end = extract_date_target(steps)
    today = date.today()
    assert start == (today - timedelta(days=10)).strftime("%Y-%m-%d")
    assert end == (today - timedelta(days=1)).strftime("%Y-%m-%d")


def test_extract_date_target_none():
    """无 set_date_range 步骤：返回 None。"""
    steps = [Step(action="click", target="查询")]
    assert extract_date_target(steps) is None
