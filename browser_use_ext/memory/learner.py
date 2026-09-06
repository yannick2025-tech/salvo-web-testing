"""从成功的 Agent 运行历史中学习元素操作记忆（设计文档第 6 节 + 无过滤策略）。

设计要点：
- 仅当任务成功时才写入记忆，失败不记录（第 6.1 节）。
- 遍历 AgentHistoryList 的步骤历史，把每一步中 Agent 真正交互过的
  DOM 元素（state.interacted_element，与 model_output.action 一一对应）
  识别出来，恢复出：元素特征 signature + 操作步骤 operation_steps + 菜单路径。
- **无过滤**：登录输入、单次点击等普通操作也一律写入记忆，让"跑过就有记忆、
  有记忆就一次定位对"生效；记忆文件几乎不设上限。
- 归并：同一页面上的连续非菜单交互折叠成一条记忆候选（复合控件=多步），
  页面 URL 变化或点击菜单则视为进入新场景而结束当前序列。
- 菜单项（menu/nav/sidebar/submenu 等）只推进菜单路径，不作为独立记忆。
- **更新策略**（配合无过滤，避免每次都重写造成 churn）：
  * 若某 key 的记忆已存在，且本次运行是"干净成功"（全程无 action error），
    则说明既有记忆仍然有效，**不覆盖**，只计入使用。
  * 若本次运行中出现过 action error（说明用记忆失败过、或前端控件变了、
    需要重试后才成功），则**用本次学习到的正确步骤覆盖**既有记忆。
- 覆盖/新增写库由 MemoryStore 统一处理（按 to_flat_string 去重）。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .models import ElementMemory, ElementSignature, MemoryContext, MemoryKey, OperationStep
from .store import MemoryStore

logger = logging.getLogger(__name__)

# 记忆参与使用的动作名前缀（命中此类动作视为"用记忆操作过"）
_MEMORY_ACTION_NAMES = {"follow_memory", "followmemory"}


@dataclass
class _PendingWidget:
    """正在累积的同一页面上的一次交互序列（可能只是单次点击/输入）。"""

    signature: ElementSignature  # 该序列首个元素特征（用于生成记忆 KEY）
    steps: list[OperationStep] = field(default_factory=list)
    url: Optional[str] = None
    title: Optional[str] = None


def _build_signature(element: object) -> Optional[ElementSignature]:
    """从 DOMInteractedElement 构建 ElementSignature。

    兼容不同 browser-use 版本字段差异：
    - node_name / tag_name: 标签名
    - attributes: 完整属性字典（含 class / aria-label / placeholder / value / role）
    - ax_name / node_value: 可见文本
    """
    if element is None:
        return None

    attributes: dict[str, object] = {}
    try:
        raw = getattr(element, "attributes", None)
        if raw is not None:
            attributes = dict(raw)
    except Exception:
        attributes = {}

    tag = str(getattr(element, "node_name", None) or getattr(element, "tag_name", None) or "div").lower()

    def _attr(key: str) -> str:
        v = attributes.get(key)
        return str(v) if v is not None else ""

    class_str = _attr("class")
    aria_label: Optional[str] = _attr("aria-label") or _attr("aria_label") or None
    role: Optional[str] = _attr("role") or None
    placeholder = _attr("placeholder")

    # 文本提取：输入类控件优先用稳定的属性锚点（placeholder/aria-label），
    # 避免用会变的当前值（如日期输入框里的 "2026-09-04"）污染记忆 KEY。
    text: Optional[str] = None
    if tag in ("input", "textarea", "select"):
        text = placeholder or aria_label or None
    if not text:
        for attr_name in ("ax_name", "node_value"):
            v = getattr(element, attr_name, None)
            if v:
                text = str(v).strip()
                break
    if not text and attributes.get("value"):
        text = str(attributes["value"]).strip()

    other_attrs: dict[str, str] = {}
    for k in ("placeholder", "name", "title", "type"):
        v = _attr(k)
        if v:
            other_attrs[k] = v

    return ElementSignature(
        tag=tag,
        role=role,
        aria_label=aria_label,
        text_fragments=[text] if text else [],
        class_fragments=class_str.split(),
        attributes=other_attrs,
    )


def _action_name_of(action: object) -> str:
    """从 agent action 模型还原动作名。"""
    name: Optional[str] = None
    try:
        n = getattr(action, "name", None)
        if n:
            name = str(n)
    except Exception:
        name = None
    if name is None:
        dump = getattr(action, "model_dump", None)
        if callable(dump):
            try:
                data = dump(exclude_unset=True)
                if isinstance(data, dict):
                    for k in data:
                        name = str(k)
                        break
            except Exception:
                name = None
    return name or "unknown"


def _is_menu_like(signature: ElementSignature) -> bool:
    """判断是否为菜单项（设计文档 4.3 的 is_menu_element 启发式）。"""
    text = " ".join(signature.text_fragments or []).lower()
    cls = " ".join(signature.class_fragments or []).lower()
    if any(kw in cls for kw in ("menu", "nav", "sidebar", "submenu")):
        return True
    if signature.role in ("menuitem", "navigation", "treeitem"):
        return True
    if signature.tag in ("nav", "menu"):
        return True
    if text and 0 < len(text) <= 12 and any(kw in cls for kw in ("菜单", "侧边栏", "nav", "menu")):
        return True
    return False


def _target_hint(sig: ElementSignature) -> str:
    """生成可读的目标提示。"""
    parts: list[str] = []
    if sig.aria_label:
        parts.append(f"「{sig.aria_label}」")
    text = " ".join(sig.text_fragments or []).strip()
    if text and text != (sig.aria_label or ""):
        parts.append(f"文本={text[:12]}")
    if sig.class_fragments:
        parts.append("." + ".".join(sig.class_fragments[:3]))
    return " ".join(parts) or sig.tag


class HistoryLearner:
    """把成功的 AgentHistoryList 解析成可写入的 ElementMemory 列表。"""

    # 单条记忆最多容纳的连续动作步数（避免把同一页上无关动作过度合并）
    _MAX_STEPS = 8

    def __init__(self, store: MemoryStore, key_mode: str = "flat") -> None:
        self.store = store
        self.key_mode = key_mode

    # ------------------------------------------------------------------ #
    # 对外主入口
    # ------------------------------------------------------------------ #
    def learn(self, history: object) -> dict[str, int]:
        """从成功历史中学习并写库。

        Args:
            history: 已确认成功（history.is_successful() is True）的历史对象。

        Returns:
            {"inserted": int, "updated": int, "skipped": int} 统计。
        """
        steps = list(getattr(history, "history", None) or [])
        had_error = _history_has_action_error(steps)
        used_memory = _history_used_memory(steps)

        menu_path: list[str] = []
        records = self._collect(steps, menu_path)

        stats = {"inserted": 0, "updated": 0, "skipped": 0}
        for rec in records:
            outcome = self._save(menu_path, rec, overwrite=had_error)
            if outcome == "updated":
                stats["updated"] += 1
            elif outcome == "inserted":
                stats["inserted"] += 1
            else:
                stats["skipped"] += 1

        logger.info(
            "记忆学习统计: 新增=%d 更新=%d 跳过=%d (本次有错误=%s 用到记忆=%s)",
            stats["inserted"], stats["updated"], stats["skipped"], had_error, used_memory,
        )
        return stats

    # ------------------------------------------------------------------ #
    # 收集：把每步交互折叠成记忆候选（不设过滤，单步也保留）
    # ------------------------------------------------------------------ #
    def _collect(self, steps: list[object], menu_path: list[str]) -> list[_PendingWidget]:
        candidates: list[_PendingWidget] = []
        pending: Optional[_PendingWidget] = None
        last_url: Optional[str] = None  # 用于检测页面跳转，跳转时重置菜单路径

        def flush() -> None:
            nonlocal pending
            if pending is not None and pending.steps:
                # 规范化步骤序号为 1..n
                for idx, s in enumerate(pending.steps, start=1):
                    s.step = idx
                candidates.append(pending)
            pending = None

        for step in steps:
            output = getattr(step, "model_output", None)
            actions = list(getattr(output, "action", None) or []) if output else []
            state = getattr(step, "state", None)
            interacted = list(getattr(state, "interacted_element", None) or [])
            page_url: Optional[str] = getattr(state, "url", None)
            page_title: Optional[str] = getattr(state, "title", None)

            # 页面跳转（URL 变化）→ 进入新场景，重置菜单路径，避免上一页的
            # 菜单路径（如"订单管理 > 充电订单列表 > ..."）污染登录页/其它页面。
            if page_url and last_url is not None and page_url != last_url:
                flush()
                menu_path.clear()
            if page_url:
                last_url = page_url

            # 失败步骤：该步的交互未成功，不作为"正确操作"学习。
            # （这也是触发覆盖更新的信号来源之一。）
            if _step_has_error(step):
                flush()
                continue

            for i, action in enumerate(actions):
                element = interacted[i] if i < len(interacted) else None
                sig = _build_signature(element)
                if sig is None:
                    continue

                # 菜单项 → 推进菜单路径，并结束当前累积
                if _is_menu_like(sig):
                    flush()
                    text = " ".join(sig.text_fragments or []).strip()
                    if text and (not menu_path or menu_path[-1] != text):
                        menu_path.append(text)
                    continue

                action_name = _action_name_of(action)
                op_step = self._make_step(sig, action_name, action)

                # 同一页面上的连续非菜单交互归并为一条记忆；
                # 页面变化或已累积满则结束当前序列。
                same_page = pending is not None and bool(page_url) and page_url == pending.url
                if pending is not None and same_page and len(pending.steps) < self._MAX_STEPS:
                    pending.steps.append(op_step)
                    continue

                flush()
                pending = _PendingWidget(
                    signature=sig,
                    steps=[op_step],
                    url=page_url,
                    title=page_title,
                )

        flush()
        return candidates

    # ------------------------------------------------------------------ #
    # 保存：应用更新策略
    # ------------------------------------------------------------------ #
    def _save(self, menu_path: list[str], rec: _PendingWidget, overwrite: bool) -> str:
        sig = rec.signature
        steps = rec.steps
        if not steps:
            return "skipped"

        element_text = " ".join(sig.text_fragments or []).strip()
        leaf_name = (
            element_text
            or (sig.aria_label or "")
            or sig.attributes.get("placeholder")
            or sig.attributes.get("name")
            or sig.tag
        )

        path = list(menu_path)
        if not path:
            path = ["未知页面"]
        path = path + [leaf_name or sig.tag]

        key = MemoryKey(
            mode=self.key_mode,
            flat_key=" > ".join(path) if self.key_mode == "flat" else "",
            hierarchical_path=path if self.key_mode == "hierarchical" else [],
        )

        key_str = key.to_flat_string()
        existing = self.store.find_by_key(key_str)

        # 已有记忆：干净成功（无需重试）则跳过，不重写，避免 churn。
        if existing is not None and not overwrite:
            self.store.note_reused(key_str)
            return "skipped"

        memory = ElementMemory(
            key=key,
            element_signature=sig,
            operation_steps=steps,
            context=MemoryContext(
                url_pattern=self._to_url_pattern(rec.url),
                page_title_fragment=self._page_fragment(rec.title),
            ),
        )
        self.store.save(memory)
        logger.info(
            "写入记忆: %s (%d 步, overwrite=%s)", key_str, len(steps), overwrite,
        )
        return "updated" if existing is not None else "inserted"

    # ------------------------------------------------------------------ #
    # 辅助
    # ------------------------------------------------------------------ #
    def _make_step(self, sig: ElementSignature, action_name: str, action: object) -> OperationStep:
        act = self._map_action(action_name)
        hint = _target_hint(sig)
        value = self._input_value(action_name, action)
        act_cn = {"click": "点击", "input": "输入", "select": "选择"}.get(act, "操作")
        desc = f"{act_cn}{hint}"
        if value:
            desc += f"，值={value}"
        return OperationStep(
            step=1,  # _collect flush 时统一编号
            description=desc,
            action=act,
            target_hint=hint,
            element_signature=sig,
            input_value=value,
        )

    def _map_action(self, action_name: str) -> str:
        if action_name in ("input_text", "set_value", "type_text", "input"):
            return "input"
        if action_name in ("select_option", "choose_option"):
            return "select"
        return "click"

    def _input_value(self, action_name: str, action: object) -> Optional[str]:
        if action_name not in ("input_text", "set_value", "type_text", "input"):
            return None
        dump = getattr(action, "model_dump", None)
        if not callable(dump):
            return None
        try:
            data = dump(exclude_unset=True)
            if isinstance(data, dict):
                for v in data.values():
                    if isinstance(v, dict):
                        return str(v.get("text") or v.get("value") or "")
        except Exception:
            pass
        return None

    @staticmethod
    def _to_url_pattern(url: Optional[str]) -> Optional[str]:
        if not url:
            return None
        try:
            from urllib.parse import urlparse

            path = urlparse(url).path or "/"
            return f"*{path}*"
        except Exception:
            return None

    @staticmethod
    def _page_fragment(title: Optional[str]) -> Optional[str]:
        if not title:
            return None
        t = " ".join(str(title).split())
        return t[:20] or None


def _step_has_error(step: object) -> bool:
    """该历史步骤是否执行失败（result 中含 error）。"""
    results = list(getattr(step, "result", None) or [])
    for r in results:
        if getattr(r, "error", None):
            return True
    return False


def _history_has_action_error(steps: list[object]) -> bool:
    """本次运行历史中是否出现过 action error（含用记忆失败、前端变化需重试等）。"""
    return any(_step_has_error(s) for s in steps)


def _history_used_memory(steps: list[object]) -> bool:
    """本次运行是否调用过 follow_memory 这类记忆动作。"""
    for step in steps:
        output = getattr(step, "model_output", None)
        actions = list(getattr(output, "action", None) or []) if output else []
        for a in actions:
            if _action_name_of(a).lower() in _MEMORY_ACTION_NAMES:
                return True
    return False
