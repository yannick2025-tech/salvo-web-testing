"""follow_memory 自定义 Action 实现。

单独成模块（且不使用 `from __future__ import annotations`）的原因：
browser-use 0.13.10 的 Registry 会对 action 函数的参数做类型归一化校验，
其中 `browser_session` 特殊参数要求**运行时真实类型**参与比较。若在带
`from __future__ import annotations` 的模块里定义，注解会被存成字符串，
导致 `BrowserSession == BrowserSession` 比较失败而抛 "conflicts with special
argument" 异常。因此这里独立成模块以避开该陷阱。

对外：integration.create_memory_agent 会把它注册进 Tools 并传给 Agent。
"""

from typing import Optional

from pydantic import BaseModel, Field

from .store import MemoryStore


class FollowMemoryParams(BaseModel):
    """follow_memory 工具参数：key 与 hint 二选一或都给。"""

    key: Optional[str] = Field(
        default=None,
        description="（可选）记忆 KEY 精确路径，如「订单管理 > 充电订单管理 > 单据时间」",
    )
    hint: Optional[str] = Field(
        default=None,
        description="（推荐）页面控件的可见文案/占位符，如「请输入账号」「单据时间」；据此自动解析记忆",
    )


def resolve_memory_key(store: MemoryStore, key: str, hint: str) -> Optional[str]:
    """根据精确 key 或语义 hint 解析出唯一记忆的 key 字符串。

    供 follow_memory 使用，让 LLM 不必死记不透明的记忆 KEY：
    传入页面里看到的控件文案（placeholder / aria / 叶子名）即可命中。
    """
    if key:
        # 先精确，再允许传入的可能是"非完整路径"做子串回退
        if store.find_by_key(key):
            return key
        for m in store.get_all():
            if key in m.key.to_flat_string():
                return m.key.to_flat_string()

    if hint:
        hint_l = hint.strip().lower()
        candidates = []
        for m in store.get_all():
            score = 0
            sig = m.element_signature
            text = " ".join(sig.text_fragments or []).lower()
            placeholder = (sig.attributes or {}).get("placeholder", "").lower()
            if sig.aria_label and sig.aria_label.lower() in hint_l:
                score += 2
            if placeholder and placeholder in hint_l:
                score += 3
            if hint_l in text:
                score += 4
            if hint_l in m.key.to_flat_string().lower():
                score += 5
            if score:
                candidates.append((score, m.key.to_flat_string()))
        if candidates:
            candidates.sort(key=lambda x: x[0], reverse=True)
            return candidates[0][1]

    return None


async def follow_memory_action(
    params: FollowMemoryParams,
    browser_session,  # BrowserSession，由 registry 注入（此模块无 future-annotations 陷阱）
):
    """按本地记忆原子执行某控件的成功操作步骤。

    LLM 无需死记不透明的记忆 KEY：传 key（精确路径）或 hint（页面控件文案，
    如 "请输入账号" / "单据时间"）即可命中并整段执行，避免对该控件反复试错。
    """
    # 惰性导入避免与 integration 形成模块加载期循环依赖
    from ..integration import _build_find_and_act_js, _current_integration
    from browser_use.agent.views import ActionResult

    if _current_integration is None:
        return ActionResult(extracted_content="记忆系统未初始化，请自行操作")

    key = params.key or ""
    hint = params.hint or ""
    resolved_key = resolve_memory_key(_current_integration.memory_store, key, hint)
    if not resolved_key:
        return ActionResult(
            extracted_content=(
                f"未找到匹配记忆(key={key}, hint={hint})，请自行操作。"
                "提示：hint 应传页面上该控件的可见文案/占位符，如“请输入账号”。"
            )
        )

    memory = _current_integration.memory_store.query_by_flat_key(resolved_key)
    if not memory:
        return ActionResult(extracted_content=f"未找到记忆: {resolved_key}，请自行操作")

    if not browser_session:
        return ActionResult(extracted_content="无法访问浏览器，请自行操作")

    results = []

    def _resolve_value(value):
        """把 @today@ / @now@ 令牌替换为真实当天日期（yyyy-MM-dd）。"""
        if not value:
            return value
        import datetime

        today = datetime.date.today().strftime("%Y-%m-%d")
        return str(value).replace("@today@", today).replace("@now@", today)

    for step in memory.operation_steps:
        try:
            sig = step.element_signature
            if not sig:
                results.append(f"步骤{step.step}: 缺少元素特征")
                continue

            # 构建 JS 查找并操作
            js = _build_find_and_act_js(sig, step.action, _resolve_value(step.input_value))

            cdp_session = await browser_session.get_or_create_cdp_session(
                target_id=browser_session.agent_focus_target_id, focus=False
            )
            await cdp_session.cdp_client.send.Runtime.evaluate(
                params={"expression": js, "returnByValue": True},
                session_id=cdp_session.session_id,
            )
            results.append(f"步骤{step.step}: ✓ {step.description}")

        except Exception as e:
            results.append(f"步骤{step.step}: ✗ {e}")
            break

    if results:
        memory.touch()
        return ActionResult(
            extracted_content=f"记忆执行完成（按记忆 {resolved_key}）:\n" + "\n".join(results)
        )

    return ActionResult(extracted_content="记忆执行失败，请自行操作")
