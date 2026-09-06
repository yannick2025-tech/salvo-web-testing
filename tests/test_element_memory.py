"""元素记忆扩展的冒烟测试（无需浏览器，纯逻辑验证）。

覆盖：
1. MemoryStore：save / query_by_flat_key / 更新（success_count +1）/ 清空
2. ElementSignature.matches：精确匹配规则
3. MemoryMatcher：flat 精确匹配 + hierarchical 前缀匹配
4. HistoryLearner：从伪造的成功历史中提取并写入记忆
5. MemoryIntegration.done_callback 成功判定逻辑（用 fake history）

运行： .venv/bin/python tests/test_element_memory.py
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from browser_use_ext.memory.learner import HistoryLearner
from browser_use_ext.memory.matcher import MemoryMatcher
from browser_use_ext.memory.models import (
    ElementMemory,
    ElementSignature,
    MemoryContext,
    MemoryKey,
    OperationStep,
)
from browser_use_ext.memory.store import MemoryStore

PASS = 0
FAIL = 0


def check(name: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✓ {name}")
    else:
        FAIL += 1
        print(f"  ✗ {name}")


def tmp_store() -> MemoryStore:
    d = tempfile.mkdtemp()
    return MemoryStore(os.path.join(d, "elements.json"), max_memories=100)


# --------------------------------------------------------------------- #
# 伪造 browser_use 对象（仅暴露 learner 需要的属性）
# --------------------------------------------------------------------- #
class FakeElement:
    def __init__(self, node_name: str, attributes: dict, ax_name: str | None = None):
        self.node_name = node_name
        self.attributes = dict(attributes)
        self.ax_name = ax_name
        self.node_value = ax_name or ""
        self.tag_name = node_name


class FakeAction:
    """模拟 agent 的 discriminated action（.name + .model_dump）"""

    def __init__(self, name: str, params: dict):
        self.name = name
        self._params = params

    def model_dump(self, exclude_unset=True):  # noqa: D401
        return {self.name: self._params}


class FakeState:
    def __init__(self, url: str, title: str, interacted: list):
        self.url = url
        self.title = title
        self.interacted_element = interacted


class _R:
    """模拟 ActionResult，可带 error。"""

    def __init__(self, error=None):
        self.error = error


class FakeHistoryStep:
    def __init__(self, state: FakeState, actions: list, error=None):
        self.state = state
        self.model_output = type("O", (), {"action": actions})
        self.result = [_R(error=error)] if error is not None else []


class FakeHistory:
    def __init__(self, steps: list, success: bool = True):
        self.history = steps
        self._success = success
        self._final = "最终报告..." if success else None

    def is_successful(self):
        return self._success

    def is_done(self):
        return self._success

    def final_result(self):
        return self._final


def test_store():
    print("\n[1] MemoryStore 读写与更新")
    store = tmp_store()
    check("初始为空", len(store.get_all()) == 0)

    mem = ElementMemory(
        key=MemoryKey(mode="flat", flat_key="订单管理 > 充电订单管理 > 单据时间下拉框"),
        element_signature=ElementSignature(
            tag="div", role="combobox", aria_label="单据时间",
            text_fragments=["账单生成时间"],
            class_fragments=["el-select", "el-input"],
        ),
        operation_steps=[
            OperationStep(step=1, description="点击下拉", action="click",
                          target_hint="el-select", element_signature=ElementSignature(tag="input")),
            OperationStep(step=2, description="选订单创建时间", action="click_option",
                          target_hint="订单创建时间", element_signature=ElementSignature(tag="li")),
        ],
        context=MemoryContext(url_pattern="*ChargeOrderManagement*"),
    )
    store.save(mem)
    check("保存后 1 条", len(store.get_all()) == 1)

    hit = store.query_by_flat_key("订单管理 > 充电订单管理 > 单据时间下拉框")
    check("按 flat key 命中", hit is not None)
    check("success_count 初始=1", hit.success_count == 1)

    # 再次保存同 key → 更新，success_count +1
    mem2 = ElementMemory(
        key=MemoryKey(mode="flat", flat_key="订单管理 > 充电订单管理 > 单据时间下拉框"),
        element_signature=mem.element_signature,
        operation_steps=mem.operation_steps,
    )
    store.save(mem2)
    all_mem = store.get_all()
    check("更新后仍 1 条", len(all_mem) == 1)
    check("success_count 更新为 2", all_mem[0].success_count == 2)
    check("updated_at 变化", all_mem[0].updated_at >= mem.updated_at)

    # 持久化
    store.reload()
    check("重载后仍 1 条", len(store.get_all()) == 1)


def test_signature_match():
    print("\n[2] ElementSignature.matches 精确匹配")
    base = ElementSignature(tag="div", role="combobox", text_fragments=["订单创建时间"],
                            class_fragments=["el-select", "el-input"])
    same = ElementSignature(tag="div", role="combobox", text_fragments=["订单创建时间"],
                            class_fragments=["el-select", "el-input", "el-select--medium"])
    check("tag+role+class 子集匹配", base.matches(same))
    wrong_tag = ElementSignature(tag="li", role="combobox", text_fragments=["订单创建时间"],
                                 class_fragments=["el-select"])
    check("tag 不一致则不匹配", not base.matches(wrong_tag))
    wrong_role = ElementSignature(tag="div", role="dialog", text_fragments=["订单创建时间"],
                                  class_fragments=["el-select", "el-input"])
    check("role 不一致则不匹配", not base.matches(wrong_role))


def _sig():
    return ElementSignature(tag="div", role="combobox", text_fragments=["订单创建时间"],
                            class_fragments=["el-select"])


def test_matcher():
    print("\n[3] MemoryMatcher flat / hierarchical")
    # flat：独立 store
    store = tmp_store()
    store.save(ElementMemory(
        key=MemoryKey(mode="flat", flat_key="订单管理 > 充电订单管理 > 单据时间下拉框"),
        element_signature=_sig(), operation_steps=[],
    ))

    m = MemoryMatcher(store=store, key_mode="flat", match_mode="exact")
    hit = m.match(["订单管理", "充电订单管理", "单据时间下拉框"], _sig())
    check("flat 精确命中", hit is not None)

    miss = m.match(["订单管理", "站点列表", "城市名称"], ElementSignature(tag="div"))
    check("flat 不相关路径不命中", miss is None)

    # hierarchical：独立 store（store.save 按 to_flat_string 去重，勿与 flat 混存）
    hstore = tmp_store()
    hstore.save(ElementMemory(
        key=MemoryKey(mode="hierarchical", hierarchical_path=["订单管理", "充电订单管理", "单据时间下拉框"]),
        element_signature=_sig(), operation_steps=[],
    ))
    mh = MemoryMatcher(store=hstore, key_mode="hierarchical", match_mode="exact")
    # 当前路径比记忆路径短（部分匹配）也应命中
    hit2 = mh.match(["订单管理", "充电订单管理"], _sig())
    check("hierarchical 前缀命中（部分匹配）", hit2 is not None)
    # 首层不同则不命中
    miss2 = mh.match(["站点管理", "站点列表", "城市名称"], _sig())
    check("hierarchical 首层不同不命中", miss2 is None)


def build_fake_order_history() -> FakeHistory:
    """伪造「订单管理 > 充电订单管理 > 单据时间设置」的完整成功历史。"""
    # 1. 点击菜单：订单管理
    s1 = FakeState("https://x/Login", "后台", [
        FakeElement("li", {"class": "el-submenu__title", "role": "menuitem"}, "订单管理")
    ])
    # 2. 点击子菜单：充电订单管理
    s2 = FakeState("https://x/ChargeOrderManagement", "充电订单管理", [
        FakeElement("li", {"class": "el-menu-item"}, "充电订单管理")
    ])
    # 3. 复合控件：单据时间下拉（3 步：点下拉→选选项→点开始日期输入框）
    s3 = FakeState("https://x/ChargeOrderManagement", "充电订单管理", [
        FakeElement("div", {"class": "el-select", "role": "combobox", "aria-label": "单据时间"}, "单据时间"),
        FakeElement("li", {"class": "el-select-dropdown__item"}, "订单创建时间"),
        FakeElement("input", {"class": "el-range-input", "placeholder": "开始日期"}, "2026-09-04"),
    ])
    a1 = FakeAction("click_element", {"index": 3})
    a2 = FakeAction("click_element", {"index": 4})
    a3 = FakeAction("input_text", {"index": 5, "text": "2026-09-04"})
    return FakeHistory([
        FakeHistoryStep(s1, [a1]),
        FakeHistoryStep(s2, [a2]),
        FakeHistoryStep(s3, [a1, a2, a3]),
    ], success=True)


def test_learner():
    print("\n[4] HistoryLearner 从成功历史学习（无过滤）")
    store = tmp_store()
    learner = HistoryLearner(store=store, key_mode="flat")
    history = build_fake_order_history()

    stats = learner.learn(history)
    check("成功历史有写入(inserted/updated>=1)",
          stats["inserted"] + stats["updated"] >= 1)

    all_mem = store.get_all()
    keys = [m.key.to_flat_string() for m in all_mem]
    print(f"    记忆 keys: {keys}")

    control_hit = any("单据时间" in k for k in keys)
    check("记录了单据时间复合控件记忆", control_hit)

    control_mem = next((m for m in all_mem if "单据时间" in m.key.to_flat_string()), None)
    if control_mem is not None:
        check(f"单据时间控件步骤数>=2（实际 {len(control_mem.operation_steps)}）",
              len(control_mem.operation_steps) >= 2)
        check("步骤序号 1..n", [s.step for s in control_mem.operation_steps] == list(range(1, len(control_mem.operation_steps) + 1)))
        check("上下文含页面标题片段", bool(control_mem.context.page_title_fragment))
        check("日期输入为子步骤（步骤含开始日期）",
              any("开始日期" in s.target_hint for s in control_mem.operation_steps))


def test_learner_login_single():
    print("\n[5] 无过滤：登录这类普通单次输入也写入记忆")
    store = tmp_store()
    learner = HistoryLearner(store=store, key_mode="flat")
    # 页面含账号输入框（单次输入）
    s = FakeState("https://x/login", "登录", [
        FakeElement("input", {"class": "el-input__inner", "placeholder": "请输入账号"}, None)
    ])
    history = FakeHistory([FakeHistoryStep(
        s, [FakeAction("input_text", {"index": 1, "text": "tester"})]
    )], success=True)
    stats = learner.learn(history)
    check("单次登录输入被写入(inserted)", stats["inserted"] == 1)
    mem = store.get_all()[0]
    key = mem.key.to_flat_string()
    print(f"    登录记忆 key: {key}")
    # 应使用 placeholder 而非会变的输入值，保证 KEY 稳定
    check("登录记忆 KEY 用 placeholder(请输入账号)", "请输入账号" in key)


def test_learner_no_rewrite_on_clean_success():
    print("\n[6] 已存在记忆 + 干净成功 → 不覆盖(只计入使用)")
    store = tmp_store()
    learner = HistoryLearner(store=store, key_mode="flat")
    s1 = FakeState("https://x/login", "登录", [
        FakeElement("input", {"class": "el-input__inner", "placeholder": "请输入账号"}, None)
    ])
    history = FakeHistory([FakeHistoryStep(
        s1, [FakeAction("input_text", {"index": 1, "text": "tester"})]
    )], success=True)

    stats1 = learner.learn(history)   # 首次：插入
    before = store.get_all()[0].success_count
    stats2 = learner.learn(history)   # 第二次：干净成功 → 跳过，success_count+1
    after = store.get_all()[0].success_count
    check("首次插入", stats1["inserted"] == 1)
    check("再次干净成功不覆盖(skipped)", stats2["skipped"] == 1)
    check("条目数仍为 1", len(store.get_all()) == 1)
    check("success_count 递增(1->2)", after == before + 1)


def test_learner_overwrite_on_error():
    print("\n[7] 本次用记忆失败(前端变了) → 覆盖更新")
    store = tmp_store()
    learner = HistoryLearner(store=store, key_mode="flat")

    # 首次成功：旧控件结构 el-select
    s1 = FakeState("https://x/orders", "订单", [
        FakeElement("div", {"class": "el-select", "role": "combobox", "aria-label": "单据时间"}, "单据时间")
    ])
    ok = FakeHistory([FakeHistoryStep(s1, [FakeAction("click_element", {"index": 1})])], success=True)
    learner.learn(ok)
    old = store.get_all()[0].operation_steps
    old_steps = [op.description for op in old]

    # 第二次：Agent 尝试旧控件时先失败(error)，再改用新结构 ant-select 成功
    fail_s = FakeState("https://x/orders", "订单", [
        FakeElement("div", {"class": "el-select", "role": "combobox", "aria-label": "单据时间"}, "单据时间")
    ])
    new_s = FakeState("https://x/orders", "订单", [
        FakeElement("div", {"class": "ant-select", "role": "combobox", "aria-label": "单据时间"}, "单据时间")
    ])
    retry = FakeHistory([
        FakeHistoryStep(fail_s, [FakeAction("click_element", {"index": 1})], error="not found"),
        FakeHistoryStep(new_s, [FakeAction("click_element", {"index": 1})]),
    ], success=True)
    stats = learner.learn(retry)
    check("失败后覆盖(updated)", stats["updated"] >= 1)

    new_steps = [op.description for op in store.get_all()[0].operation_steps]
    print(f"    旧步骤: {old_steps}")
    print(f"    新步骤: {new_steps}")
    # 失败步骤(el-select)被跳过学习，只学习成功的新结构 ant-select
    check("覆盖后记录了新控件结构(ant-select)",
          any("ant-select" in d for d in new_steps))
    check("不再学习失败步骤(el-select)",
          not any("el-select" in d for d in new_steps))
    # 覆盖后仍算一次成功使用（success_count 至少保留），证明记忆仍在被复用
    check("覆盖更新后成功次数 >=1", store.get_all()[0].success_count >= 1)


def test_integration_success_logic():
    print("\n[6] done_callback 成功判定（不误学失败任务）")
    from browser_use_ext.integration import MemoryIntegration
    from browser_use_ext.memory.models import AppConfig

    # 用临时存储，避免污染真实 memory/elements.json（其可能已有种子记忆）
    d = tempfile.mkdtemp()
    cfg = AppConfig()
    cfg.element_memory.auto_learn = True
    cfg.element_memory.storage_path = os.path.join(d, "elements.json")
    integ = MemoryIntegration(cfg)
    before = len(integ.memory_store.get_all())
    # 失败历史 → 不应新增记忆
    fail_history = FakeHistory([FakeHistoryStep(
        FakeState("https://x/Login", "登录", [FakeElement("input", {"class": "el-input__inner"}, "账号")]),
        [FakeAction("input_text", {"index": 1, "text": "x"})],
    )], success=False)
    import asyncio
    asyncio.run(integ.done_callback(fail_history))
    check("失败任务不学习", len(integ.memory_store.get_all()) == before)


def test_resolve_memory_key():
    print("\n[8] resolve_memory_key：follow_memory 记忆解析")
    from browser_use_ext.integration import resolve_memory_key

    store = tmp_store()
    store.save(ElementMemory(
        key=MemoryKey(mode="flat", flat_key="订单管理 > 充电订单管理 > 单据时间"),
        element_signature=ElementSignature(
            tag="div", role="combobox", text_fragments=["订单创建时间"],
            class_fragments=["el-select"]),
        operation_steps=[],
    ))
    store.save(ElementMemory(
        key=MemoryKey(mode="flat", flat_key="未知页面 > 请输入账号"),
        element_signature=ElementSignature(
            tag="input", attributes={"placeholder": "请输入账号"},
            text_fragments=["请输入账号"], class_fragments=["el-input"]),
        operation_steps=[],
    ))

    check("exact key 命中",
          resolve_memory_key(store, "订单管理 > 充电订单管理 > 单据时间", "") == "订单管理 > 充电订单管理 > 单据时间")
    check("key 子串回退命中",
          resolve_memory_key(store, "单据时间", "") == "订单管理 > 充电订单管理 > 单据时间")
    check("hint 占位符命中",
          resolve_memory_key(store, "", "请输入账号") == "未知页面 > 请输入账号")
    check("hint 文本命中",
          resolve_memory_key(store, "", "订单创建时间") == "订单管理 > 充电订单管理 > 单据时间")
    check("无匹配返回 None",
          resolve_memory_key(store, "", "完全不存在的东西") is None)


if __name__ == "__main__":
    print("元素记忆扩展 冒烟测试")
    test_store()
    test_signature_match()
    test_matcher()
    test_learner()
    test_learner_login_single()
    test_learner_no_rewrite_on_clean_success()
    test_learner_overwrite_on_error()
    test_integration_success_logic()
    test_resolve_memory_key()
    print(f"\n结果: {PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)
