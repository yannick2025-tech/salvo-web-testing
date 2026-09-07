"""元素记忆扩展的单元测试（无需浏览器，纯逻辑验证）。

覆盖：
1. MemoryStore：save / query_by_flat_key / 更新（success_count +1）/ 持久化
2. ElementSignature.matches：精确匹配规则
3. MemoryMatcher：flat 精确匹配 + hierarchical 前缀匹配
4. HistoryLearner：从伪造的成功历史中提取并写入记忆
5. MemoryIntegration.done_callback 成功判定逻辑（用 fake history）
6. ShardedMemoryStore：平台 + URL path 第一段分片路由、_common 分片、单文件回退

运行：
    uv sync --extra dev      # 首次安装 pytest
    uv run pytest -q         # 全量运行
    uv run pytest tests/test_element_memory.py -v   # 单文件详细运行
"""

from __future__ import annotations

import asyncio
import json
import os

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


def _sig():
    return ElementSignature(tag="div", role="combobox", text_fragments=["订单创建时间"],
                            class_fragments=["el-select"])


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


# --------------------------------------------------------------------- #
# 测试
# --------------------------------------------------------------------- #
def test_store(tmp_path):
    store = MemoryStore(str(tmp_path / "elements.json"), max_memories=100)
    assert len(store.get_all()) == 0, "初始应为空"

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
    assert len(store.get_all()) == 1, "保存后应有 1 条"

    hit = store.query_by_flat_key("订单管理 > 充电订单管理 > 单据时间下拉框")
    assert hit is not None, "按 flat key 应命中"
    assert hit.success_count == 1, "success_count 初始应为 1"

    # 再次保存同 key → 更新，success_count +1
    mem2 = ElementMemory(
        key=MemoryKey(mode="flat", flat_key="订单管理 > 充电订单管理 > 单据时间下拉框"),
        element_signature=mem.element_signature,
        operation_steps=mem.operation_steps,
    )
    store.save(mem2)
    all_mem = store.get_all()
    assert len(all_mem) == 1, "更新后仍应 1 条"
    assert all_mem[0].success_count == 2, "success_count 应更新为 2"
    assert all_mem[0].updated_at >= mem.updated_at, "updated_at 应变化"

    # 持久化
    store.reload()
    assert len(store.get_all()) == 1, "重载后仍应 1 条"


def test_signature_match():
    base = ElementSignature(tag="div", role="combobox", text_fragments=["订单创建时间"],
                            class_fragments=["el-select", "el-input"])
    same = ElementSignature(tag="div", role="combobox", text_fragments=["订单创建时间"],
                            class_fragments=["el-select", "el-input", "el-select--medium"])
    assert base.matches(same), "tag+role+class 子集应匹配"
    wrong_tag = ElementSignature(tag="li", role="combobox", text_fragments=["订单创建时间"],
                                 class_fragments=["el-select"])
    assert not base.matches(wrong_tag), "tag 不一致不应匹配"
    wrong_role = ElementSignature(tag="div", role="dialog", text_fragments=["订单创建时间"],
                                  class_fragments=["el-select", "el-input"])
    assert not base.matches(wrong_role), "role 不一致不应匹配"


def test_matcher(tmp_path):
    # flat：独立 store
    store = MemoryStore(str(tmp_path / "flat.json"), max_memories=100)
    store.save(ElementMemory(
        key=MemoryKey(mode="flat", flat_key="订单管理 > 充电订单管理 > 单据时间下拉框"),
        element_signature=_sig(), operation_steps=[],
    ))

    m = MemoryMatcher(store=store, key_mode="flat", match_mode="exact")
    hit = m.match(["订单管理", "充电订单管理", "单据时间下拉框"], _sig())
    assert hit is not None, "flat 精确命中"

    miss = m.match(["订单管理", "站点列表", "城市名称"], ElementSignature(tag="div"))
    assert miss is None, "flat 不相关路径不应命中"

    # hierarchical：独立 store（store.save 按 to_flat_string 去重，勿与 flat 混存）
    hstore = MemoryStore(str(tmp_path / "hier.json"), max_memories=100)
    hstore.save(ElementMemory(
        key=MemoryKey(mode="hierarchical", hierarchical_path=["订单管理", "充电订单管理", "单据时间下拉框"]),
        element_signature=_sig(), operation_steps=[],
    ))
    mh = MemoryMatcher(store=hstore, key_mode="hierarchical", match_mode="exact")
    # 当前路径比记忆路径短（部分匹配）也应命中
    hit2 = mh.match(["订单管理", "充电订单管理"], _sig())
    assert hit2 is not None, "hierarchical 前缀命中（部分匹配）"
    # 首层不同则不命中
    miss2 = mh.match(["站点管理", "站点列表", "城市名称"], _sig())
    assert miss2 is None, "hierarchical 首层不同不应命中"


def test_learner(tmp_path):
    store = MemoryStore(str(tmp_path / "elements.json"), max_memories=100)
    learner = HistoryLearner(store=store, key_mode="flat")
    history = build_fake_order_history()

    stats = learner.learn(history)
    assert stats["inserted"] + stats["updated"] >= 1, "成功历史应有写入"

    all_mem = store.get_all()
    keys = [m.key.to_flat_string() for m in all_mem]

    control_hit = any("单据时间" in k for k in keys)
    assert control_hit, "记录了单据时间复合控件记忆"

    control_mem = next((m for m in all_mem if "单据时间" in m.key.to_flat_string()), None)
    assert control_mem is not None
    assert len(control_mem.operation_steps) >= 2, "单据时间控件步骤数应 >= 2"
    assert [s.step for s in control_mem.operation_steps] == list(
        range(1, len(control_mem.operation_steps) + 1)
    ), "步骤序号应为 1..n"
    assert bool(control_mem.context.page_title_fragment), "上下文应含页面标题片段"
    assert any("开始日期" in s.target_hint for s in control_mem.operation_steps), \
        "日期输入应为子步骤（步骤含开始日期）"


def test_learner_login_single(tmp_path):
    store = MemoryStore(str(tmp_path / "elements.json"), max_memories=100)
    learner = HistoryLearner(store=store, key_mode="flat")
    # 页面含账号输入框（单次输入）
    s = FakeState("https://x/login", "登录", [
        FakeElement("input", {"class": "el-input__inner", "placeholder": "请输入账号"}, None)
    ])
    history = FakeHistory([FakeHistoryStep(
        s, [FakeAction("input_text", {"index": 1, "text": "tester"})]
    )], success=True)
    stats = learner.learn(history)
    assert stats["inserted"] == 1, "单次登录输入应被写入(inserted)"
    mem = store.get_all()[0]
    key = mem.key.to_flat_string()
    # 应使用 placeholder 而非会变的输入值，保证 KEY 稳定
    assert "请输入账号" in key, "登录记忆 KEY 应用 placeholder(请输入账号)"


def test_learner_no_rewrite_on_clean_success(tmp_path):
    store = MemoryStore(str(tmp_path / "elements.json"), max_memories=100)
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
    assert stats1["inserted"] == 1, "首次应插入"
    assert stats2["skipped"] == 1, "再次干净成功不应覆盖(skipped)"
    assert len(store.get_all()) == 1, "条目数应仍为 1"
    assert after == before + 1, "success_count 应递增(1->2)"


def test_learner_overwrite_on_error(tmp_path):
    store = MemoryStore(str(tmp_path / "elements.json"), max_memories=100)
    learner = HistoryLearner(store=store, key_mode="flat")

    # 首次成功：旧控件结构 el-select
    s1 = FakeState("https://x/orders", "订单", [
        FakeElement("div", {"class": "el-select", "role": "combobox", "aria-label": "单据时间"}, "单据时间")
    ])
    ok = FakeHistory([FakeHistoryStep(s1, [FakeAction("click_element", {"index": 1})])], success=True)
    learner.learn(ok)
    old_steps = [op.description for op in store.get_all()[0].operation_steps]

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
    assert stats["updated"] >= 1, "失败后应覆盖(updated)"

    new_steps = [op.description for op in store.get_all()[0].operation_steps]
    # 失败步骤(el-select)被跳过学习，只学习成功的新结构 ant-select
    assert any("ant-select" in d for d in new_steps), "覆盖后应记录新控件结构(ant-select)"
    assert not any("el-select" in d for d in new_steps), "不应再学习失败步骤(el-select)"
    # 覆盖后仍算一次成功使用（success_count 至少保留），证明记忆仍在被复用
    assert store.get_all()[0].success_count >= 1, "覆盖更新后成功次数应 >= 1"


def test_integration_success_logic(tmp_path):
    from browser_use_ext.integration import MemoryIntegration
    from browser_use_ext.memory.models import AppConfig

    # 用临时存储，避免污染真实 memory/elements.json（其可能已有种子记忆）
    cfg = AppConfig()
    cfg.element_memory.auto_learn = True
    cfg.element_memory.storage_path = str(tmp_path / "elements.json")
    integ = MemoryIntegration(cfg)
    before = len(integ.memory_store.get_all())
    # 失败历史 → 不应新增记忆
    fail_history = FakeHistory([FakeHistoryStep(
        FakeState("https://x/Login", "登录", [FakeElement("input", {"class": "el-input__inner"}, "账号")]),
        [FakeAction("input_text", {"index": 1, "text": "x"})],
    )], success=False)
    asyncio.run(integ.done_callback(fail_history))
    assert len(integ.memory_store.get_all()) == before, "失败任务不应学习"


def test_resolve_memory_key(tmp_path):
    from browser_use_ext.integration import resolve_memory_key

    store = MemoryStore(str(tmp_path / "elements.json"), max_memories=100)
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

    assert resolve_memory_key(store, "订单管理 > 充电订单管理 > 单据时间", "") == \
        "订单管理 > 充电订单管理 > 单据时间", "exact key 应命中"
    assert resolve_memory_key(store, "单据时间", "") == \
        "订单管理 > 充电订单管理 > 单据时间", "key 子串应回退命中"
    assert resolve_memory_key(store, "", "请输入账号") == \
        "未知页面 > 请输入账号", "hint 占位符应命中"
    assert resolve_memory_key(store, "", "订单创建时间") == \
        "订单管理 > 充电订单管理 > 单据时间", "hint 文本应命中"
    assert resolve_memory_key(store, "", "完全不存在的东西") is None, "无匹配应返回 None"


def test_sharded_store(tmp_path):
    from browser_use_ext.memory.store import ShardedMemoryStore

    d = str(tmp_path)
    s = ShardedMemoryStore(d, platform_alias="manhattan", platform_host="example-platform.com")

    def mk(key, url, host):
        return ElementMemory(
            key=MemoryKey(mode="flat", flat_key=key),
            element_signature=ElementSignature(tag="input", class_fragments=["el-input"]),
            operation_steps=[OperationStep(step=1, description="x", action="click",
                                           element_signature=ElementSignature(tag="input"))],
            context=MemoryContext(url_pattern=url, host=host),
        )

    host = "example-platform.com"
    s.save(mk("登录 > 账号", "*Login*", host))
    s.save(mk("充电 > 单据时间", "*order/charge-order/list*", host))
    s.save(mk("站点 > 城市名称", "*station/site/list*", host))

    assert len(s.get_all()) == 3, "聚合读取应 3 条"
    assert os.path.exists(os.path.join(d, "manhattan", "_common.json")), \
        "manhattan/_common.json 应存在"
    assert os.path.exists(os.path.join(d, "manhattan", "order.json")), \
        "manhattan/order.json 应存在"
    assert os.path.exists(os.path.join(d, "manhattan", "station.json")), \
        "manhattan/station.json 应存在"
    assert len(json.load(open(os.path.join(d, "manhattan", "_common.json")))["memories"]) == 1, \
        "登录页应落入 _common 分片"
    assert len(json.load(open(os.path.join(d, "manhattan", "order.json")))["memories"]) == 1, \
        "order 分片应 1 条"
    assert len(json.load(open(os.path.join(d, "manhattan", "station.json")))["memories"]) == 1, \
        "station 分片应 1 条"

    hit = s.query_by_flat_key("充电 > 单据时间")
    assert hit is not None, "flat key 跨分片应命中"


def test_sharded_resolve_shard():
    from browser_use_ext.memory.store import ShardedMemoryStore

    assert ShardedMemoryStore.resolve_shard("https://x/station/site/list") == "station.json", \
        "一级菜单 station -> station.json"
    assert ShardedMemoryStore.resolve_shard("/order/charge-order/list") == "order.json", \
        "一级菜单 order -> order.json"
    assert ShardedMemoryStore.resolve_shard("https://x/Login") == "_common.json", \
        "登录页 -> _common.json"
    assert ShardedMemoryStore.resolve_shard("") == "_common.json", "空 path -> _common.json"


def test_sharded_no_platform_fallback(tmp_path):
    from browser_use_ext.memory.store import ShardedMemoryStore

    d = str(tmp_path)
    s = ShardedMemoryStore(d)  # 无 platform_alias
    mem = ElementMemory(
        key=MemoryKey(mode="flat", flat_key="通用 > 按钮"),
        element_signature=ElementSignature(tag="input"),
        operation_steps=[],
        context=MemoryContext(url_pattern="*/other*", host="some.host"),
    )
    s.save(mem)
    assert os.path.exists(os.path.join(d, "elements.json")), \
        "无平台上下文应写入 default elements.json"
    assert len(s.get_all()) == 1, "应读取 1 条"
