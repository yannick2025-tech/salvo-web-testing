"""Agent 集成模块：弹窗自动关闭 + 元素操作记忆

通过 browser-use Agent 的回调机制和自定义 Tool 实现：
- 轨道1: extend_system_message 注入记忆提示（软约束）
- 轨道2: follow_memory 自定义 Tool（中约束）
- 弹窗: register_new_step_callback 中调用 BusinessPopupWatchdog.scan()
- 记忆写入: register_done_callback 中自动学习
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Optional

from browser_use.agent.views import AgentOutput
from browser_use.browser.views import BrowserStateSummary

from .memory.follow_memory import FollowMemoryParams, follow_memory_action, resolve_memory_key
from .memory.matcher import MemoryMatcher
from .memory.models import (
    AppConfig,
    ElementMemory,
    ElementSignature,
    MemoryKey,
    OperationStep,
)
from .memory.store import MemoryStore
from .watchdogs.business_popup_watchdog import BusinessPopupWatchdog

logger = logging.getLogger(__name__)

# P0 级 prompt 约束指令
MEMORY_RULE_PROMPT = """
[规则-P0-必须遵守] 元素操作记忆规则：
1. 当你准备操作某个控件（输入框/下拉框/级联/日期/复选框/按钮等）时，优先尝试用
   follow_memory 工具查证本地记忆，并把 hint 设为你看到的控件文案/占位符
   （如“请输入账号”“单据时间”），或传 key 记忆路径。
2. 若 follow_memory 返回成功，说明该控件已按记忆原子执行完成，直接继续下一步，
   不要对该控件再次自行探索/试错。
3. 若 follow_memory 返回“未找到匹配记忆”或执行失败，才回退到自行操作并逐步试错。
4. 按记忆操作成功后，标记该步骤为 done，不重复操作。
5. 系统可能在下文给出「元素操作记忆」区块，其中记忆与你当前 DOM 匹配时应优先遵守。
6. 违反以上规则将导致任务失败。
"""


class MemoryIntegration:
    """记忆系统集成：管理弹窗扫描、记忆查询注入和记忆写入"""

    def __init__(self, config: AppConfig):
        self.config = config

        # 弹窗 watchdog
        self.popup_watchdog = BusinessPopupWatchdog(config.popup_watchdog)

        # 记忆存储和匹配
        mem_config = config.element_memory
        if getattr(mem_config, "sharding_enabled", False):
            from .memory.store import ShardedMemoryStore

            self.memory_store = ShardedMemoryStore(
                mem_config.shard_dir,
                platform_alias=getattr(mem_config, "platform_alias", "") or "",
                platform_host=getattr(mem_config, "platform_host", "") or "",
            )
        else:
            self.memory_store = MemoryStore(
                storage_path=mem_config.storage_path,
                max_memories=mem_config.max_memories,
            )
        self.memory_matcher = MemoryMatcher(
            store=self.memory_store,
            key_mode=mem_config.key_mode,
            match_mode=mem_config.match_mode,
        )

        # 运行时状态
        self._menu_path: list[str] = []  # 当前推断的菜单路径
        self._step_memory_hints: list[str] = []  # 当前步的记忆提示
        self._browser_session: Any = None  # 保存 browser_session 引用

    def _infer_menu_path_from_output(
        self, agent_output: AgentOutput, state: BrowserStateSummary
    ) -> list[str]:
        """
        从 Agent 输出和页面状态推断菜单路径。

        策略：
        - 如果 Agent 点击了包含 'menu'/'nav'/'sidebar' 相关 class 或 role=menuitem 的元素，记录为菜单层
        - 同时利用页面 title 辅助推断
        """
        path = list(self._menu_path)  # 保留历史菜单路径

        try:
            if agent_output and agent_output.action:
                for action_model in agent_output.action:
                    action_data = action_model.model_dump(exclude_unset=True)
                    for action_name, action_params in action_data.items():
                        if action_name == "click_element" and isinstance(action_params, dict):
                            index = action_params.get("index")
                            if index is not None and state.dom_state and state.dom_state.selector_map:
                                element_info = state.dom_state.selector_map.get(index)
                                if element_info and self._is_menu_element(element_info):
                                    text = getattr(element_info, "text", "") or ""
                                    if text:
                                        path.append(text.strip())
        except Exception as e:
            logger.debug(f"推断菜单路径失败: {e}")

        return path

    def _is_menu_element(self, element_info: Any) -> bool:
        """判断元素是否为菜单项"""
        try:
            classes = getattr(element_info, "class_name", "") or ""
            if any(kw in classes.lower() for kw in ["menu", "nav", "sidebar", "submenu"]):
                return True
            role = getattr(element_info, "role", "") or ""
            if role in ("menuitem", "navigation", "treeitem"):
                return True
            tag = getattr(element_info, "tag_name", "") or ""
            if tag in ("nav", "menu"):
                return True
        except Exception:
            pass
        return False

    def _extract_element_signatures_from_state(
        self, state: BrowserStateSummary
    ) -> list[dict]:
        """从 DOM 状态提取元素特征列表"""
        signatures = []
        try:
            if state.dom_state and state.dom_state.selector_map:
                for index, element_info in state.dom_state.selector_map.items():
                    sig = {
                        "index": index,
                        "tag": getattr(element_info, "tag_name", ""),
                        "role": getattr(element_info, "role", ""),
                        "text": getattr(element_info, "text", ""),
                        "class_fragments": (
                            getattr(element_info, "class_name", "").split()
                            if getattr(element_info, "class_name", "")
                            else []
                        ),
                    }
                    signatures.append(sig)
        except Exception as e:
            logger.debug(f"提取元素特征失败: {e}")
        return signatures

    def _query_memory(self, state: BrowserStateSummary) -> list[str]:
        """查询记忆，返回格式化的提示文本列表"""
        hints = []

        if not self.config.element_memory.enabled:
            return hints

        try:
            element_sigs = self._extract_element_signatures_from_state(state)

            for esig in element_sigs:
                element_signature = ElementSignature(
                    tag=esig.get("tag", "div"),
                    role=esig.get("role") or None,
                    text_fragments=[esig.get("text", "")] if esig.get("text") else [],
                    class_fragments=esig.get("class_fragments", []),
                )

                menu_path = self._menu_path + [esig.get("text", "")]

                memory = self.memory_matcher.match(
                    menu_path=menu_path,
                    element_signature=element_signature,
                )

                if memory:
                    hint = self.memory_matcher.format_memory_for_prompt(memory)
                    hints.append(hint)
                    logger.info(f"命中记忆: {' > '.join(menu_path)}")

        except Exception as e:
            logger.debug(f"记忆查询失败: {e}")

        return hints

    async def step_callback(
        self, state: BrowserStateSummary, agent_output: AgentOutput, step: int
    ) -> None:
        """每步回调：弹窗扫描 + 记忆查询注入"""
        try:
            # 1. 弹窗扫描
            if self.config.popup_watchdog.scan_on_step and self._browser_session:
                await self.popup_watchdog.scan(self._browser_session)

            # 2. 推断菜单路径
            self._menu_path = self._infer_menu_path_from_output(agent_output, state)

            # 3. 查询记忆
            self._step_memory_hints = self._query_memory(state)

        except Exception as e:
            logger.debug(f"step_callback 执行失败: {e}")

    async def done_callback(self, history: Any) -> None:
        """完成回调：自动学习记忆（设计文档第 6 节）"""
        if not self.config.element_memory.auto_learn:
            return

        try:
            # 任务是否真正成功：AgentHistoryList.is_successful() 返回
            # True / False / None（None 表示尚未完成）。注意 final_result()
            # 只返回 extracted_content 字符串，并没有 .success 字段。
            is_success = None
            for name in ("is_successful", "is_validated"):
                fn = getattr(history, name, None)
                if callable(fn):
                    try:
                        is_success = fn()
                    except Exception:
                        is_success = None
                    if is_success is not None:
                        break

            if is_success is not True:
                logger.info("任务未明确成功，跳过记忆学习")
                return

            # 从历史中提取并写入记忆
            self._learn_from_history(history)

        except Exception as e:
            logger.debug(f"done_callback 学习失败: {e}")

    def _learn_from_history(self, history: Any) -> None:
        """从成功的 Agent 历史中提取元素操作记忆并写入。"""
        from .memory.learner import HistoryLearner

        mem_config = self.config.element_memory
        learner = HistoryLearner(
            store=self.memory_store,
            key_mode=mem_config.key_mode,
        )
        stats = learner.learn(history)
        logger.info(
            "记忆学习完成：新增=%d 更新=%d 跳过=%d，当前共 %d 条",
            stats.get("inserted", 0),
            stats.get("updated", 0),
            stats.get("skipped", 0),
            len(self.memory_store.get_all()),
        )

    def get_system_message_extension(self) -> str:
        """获取需要追加到 system message 的内容"""
        if not self._step_memory_hints:
            return ""
        parts = [MEMORY_RULE_PROMPT]
        for hint in self._step_memory_hints:
            parts.append(hint)
        return "\n".join(parts)

    def query_memory_hints(self, state: BrowserStateSummary) -> list[str]:
        """针对当步最新 DOM 查询命中记忆，返回可操作提示列表。

        与 step_callback 里的 _query_memory 不同：此方法直接以当前步新抓取的
        browser_state_summary 为依据（它携带当步 DOM 的 selector_map 与索引），
        从而把记忆与"LLM 即将操作的 DOM 元素索引"绑定起来，更精确。
        """
        hints = []
        if not self.config.element_memory.enabled or not self.memory_store.get_all():
            return hints
        try:
            mem_config = self.config.element_memory
            current_path = list(self._menu_path)
            if not state or not state.dom_state or not state.dom_state.selector_map:
                return hints

            matched_keys = set()
            for index, element_info in state.dom_state.selector_map.items():
                sig = ElementSignature(
                    tag=getattr(element_info, "tag_name", "") or "div",
                    role=getattr(element_info, "role", "") or None,
                    text_fragments=[getattr(element_info, "text", "")] or [],
                    class_fragments=(
                        getattr(element_info, "class_name", "").split()
                        if getattr(element_info, "class_name", "")
                        else []
                    ),
                )
                for depth in range(len(current_path), -1, -1):
                    path = current_path[:depth] + [sig.text_fragments[0] if sig.text_fragments else ""]
                    memory = self.memory_matcher.match(
                        menu_path=[p for p in path if p],
                        element_signature=sig,
                    )
                    if memory:
                        key = memory.key.to_flat_string()
                        if key in matched_keys:
                            break
                        matched_keys.add(key)
                        text = (sig.text_fragments[0] if sig.text_fragments else "") or sig.aria_label or "元素"
                        steps_desc = "; ".join(
                            f"{s.step}) {s.description}" for s in memory.operation_steps[:4]
                        )
                        hints.append(
                            f"[元素操作记忆] DOM 索引 {index} 命中记忆“{key}”，"
                            f"该控件按记忆应执行: {steps_desc}。建议直接调用 follow_memory"
                            f"(hint={text!r}) 原子执行，勿再自行试错。"
                        )
                        break
        except Exception as e:
            logger.debug(f"当步记忆命中查询失败: {e}")
        return hints

    def inject_memory_hints_into_context(self, agent: Any, state: BrowserStateSummary) -> None:
        """把命中记忆注入到本次 LLM 决策前的上下文（软引导，轨道1）。

        依赖 browser-use 私有的 _add_context_message，全部 try/except 保护，
        任何失败都不影响 Agent 主流程。
        """
        if not self.config.element_memory.enabled:
            return
        hints = self.query_memory_hints(state)
        if not hints:
            return
        try:
            from browser_use.llm.messages import UserMessage

            msg = "【元素操作记忆-请优先遵守】\n" + "\n".join(hints)
            mm = getattr(agent, "_message_manager", None)
            add = getattr(mm, "_add_context_message", None)
            if callable(add):
                add(UserMessage(content=msg))
                logger.info(f"已注入 {len(hints)} 条记忆提示到 LLM 上下文")
            else:
                logger.debug("message_manager 不支持注入上下文，跳过")
        except Exception as e:
            logger.debug(f"记忆上下文注入失败(不影响主流程): {e}")

    def save_memory(
        self,
        flat_key: str,
        element_signature: ElementSignature,
        operation_steps: list[OperationStep],
        url_pattern: str | None = None,
        page_title_fragment: str | None = None,
    ) -> None:
        """手动保存一条记忆（用于测试或手动录入）"""
        from .memory.models import MemoryContext

        memory = ElementMemory(
            key=MemoryKey(mode="flat", flat_key=flat_key),
            element_signature=element_signature,
            operation_steps=operation_steps,
            context=MemoryContext(
                url_pattern=url_pattern,
                page_title_fragment=page_title_fragment,
            ),
        )
        self.memory_store.save(memory)


def _load_config(config_path: str) -> AppConfig:
    """加载配置文件"""
    path = Path(config_path)
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return AppConfig.model_validate(data)
        except Exception as e:
            logger.warning(f"配置文件加载失败，使用默认配置: {e}")
    return AppConfig()


# 全局引用（由 create_memory_agent 设置）
_current_integration: Optional[MemoryIntegration] = None


def _build_find_and_act_js(
    sig: ElementSignature, action: str, input_value: str | None = None
) -> str:
    """构建查找元素并执行操作的 JS 脚本"""
    text_frags = json.dumps(sig.text_fragments, ensure_ascii=False)
    class_frags = json.dumps(sig.class_fragments, ensure_ascii=False)
    aria_label = json.dumps(sig.aria_label, ensure_ascii=False) if sig.aria_label else "null"
    tag_selector = sig.tag or "*"

    if action == "click":
        act_js = 'el.click(); return "clicked";'
    elif action == "input":
        val = json.dumps(input_value or "", ensure_ascii=False)
        act_js = 'el.value = %s; el.dispatchEvent(new Event("input", {bubbles: true})); return "input";' % val
    elif action == "input_enter":
        # Element UI / 定制日期选择器：只设 value 不生效，需用原生 setter(触发 Vue)
        # + 派发 input + Enter 确认。对 el-range-input 两个框都会执行。
        val = json.dumps(input_value or "", ensure_ascii=False)
        act_js = (
            "(function(){\n"
            "  const proto = el instanceof HTMLInputElement ? HTMLInputElement.prototype : HTMLTextAreaElement.prototype;\n"
            "  const setter = Object.getOwnPropertyDescriptor(proto, 'value').set;\n"
            "  setter.call(el, ''); el.dispatchEvent(new Event('input', {bubbles: true}));\n"
            "  setter.call(el, %s); el.dispatchEvent(new Event('input', {bubbles: true}));\n"
            "  el.focus();\n"
            "  el.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', code:'Enter', bubbles:true, cancelable:true}));\n"
            "  el.dispatchEvent(new KeyboardEvent('keyup', {key:'Enter', code:'Enter', bubbles:true}));\n"
            "  el.dispatchEvent(new Event('change', {bubbles: true}));\n"
            "  return 'input_enter';\n"
            "})();"
        ) % val
    else:
        act_js = 'el.click(); return "acted";'

    # 使用字符串拼接避免 f-string 中 JS 单引号/花括号冲突
    js_parts = [
        "(function() {",
        "  const textFrags = %s;" % text_frags,
        "  const classFrags = %s;" % class_frags,
        "  const ariaLabel = %s;" % aria_label,
        "",
        '  const elements = document.querySelectorAll("%s");' % tag_selector,
        "  for (const el of elements) {",
        "    const classMatch = classFrags.length === 0 || classFrags.some(c => el.classList.contains(c));",
        "    const textMatch = textFrags.length === 0 || textFrags.some(t => el.textContent && el.textContent.includes(t));",
        '    const ariaMatch = ariaLabel === null || (el.getAttribute("aria-label") && el.getAttribute("aria-label").includes(ariaLabel));',
        "",
        "    if (classMatch && (textMatch || ariaMatch)) {",
        "      %s" % act_js,
        "    }",
        "  }",
        '  return "not_found";',
        "})();",
    ]
    return "\n".join(js_parts)


def create_memory_agent(
    task: str,
    llm: Any,
    config_path: str = "./memory/config.json",
    config: Any = None,
    **kwargs,
) -> Any:
    """
    创建集成了弹窗自动关闭和元素操作记忆的 Agent。

    Args:
        task: 任务描述
        llm: LLM 实例
        config_path: 配置文件路径（JSON）；当未传 config 时使用。
        config: 可选，直接传入的 AppConfig 对象（优先于 config_path）。
        **kwargs: 其他 Agent 参数

    Returns:
        配置好的 Agent 实例
    """
    global _current_integration

    from browser_use import Agent, Tools

    # 1. 加载配置：优先用直接传入的 config 对象，否则读 config_path
    config = config if config is not None else _load_config(config_path)

    # 2. 创建记忆集成实例
    integration = MemoryIntegration(config)
    _current_integration = integration

    # 3. 构造 Tools（自带全部默认浏览器动作）并注册自定义 Tool: follow_memory
    # browser-use 0.13.10 中 Registry.action 是"装饰器"：name 取自函数 __name__，
    # 且需通过 Tools(...) 传给 Agent（Agent 要求 tools 是 Tools，而非裸 Registry）。
    tools = Tools()
    try:
        tools.registry.action(
            description=(
                "按本地记忆原子执行某控件的成功操作步骤。当你发现当前页面某控件（下拉框/级联/"
                "日期/输入框等）之前操作过且系统提示提示你有记忆时，调用本工具并传 hint=该控件文案"
                "（或 key=记忆路径），即可一步完成，无需再逐步试错。"
            ),
            param_model=FollowMemoryParams,
        )(follow_memory_action)
        logger.info("已注册 follow_memory Tool")
    except Exception as e:
        logger.warning(f"注册 follow_memory Tool 失败: {e}")

    # 4. 构建系统消息扩展
    system_message = integration.get_system_message_extension()

    # 5. 创建回调
    # 说明：browser_session 引用统一由下方 patched_run 在 agent.run 启动时
    # 从 agent.browser_session 注入，因此此处不再做脆弱的属性探测。
    async def step_cb(state: BrowserStateSummary, agent_output: AgentOutput, step: int) -> None:
        # 确保 session 引用就绪（极端情况下 run 前若已有 session 直接补注入）
        if integration._browser_session is None and hasattr(agent, "browser_session"):
            integration._browser_session = agent.browser_session

        await integration.step_callback(state, agent_output, step)

        # 记忆提示可能随步骤变化（用于调试/日志，最终由轨道2 tool 兜底执行）
        new_ext = integration.get_system_message_extension()
        if new_ext:
            logger.debug(f"记忆提示已更新: {new_ext[:100]}...")

    async def done_cb(history: Any) -> None:
        if integration._browser_session is None and hasattr(agent, "browser_session"):
            integration._browser_session = agent.browser_session

        await integration.done_callback(history)

    # 6. 合并 tools：若调用方传了自定义 tools，把 follow_memory 动作合并进去；否则用本 tools
    def _inner_actions(tool_obj: Any) -> dict:
        """拿到某个 tools 对象内部注册动作的 dict（兼容 Tools/Controller/Registry）。"""
        reg = getattr(tool_obj, "registry", None)
        if reg is None:
            return {}
        # outer Registry 内部还包了一层 ActionRegistry(.registry)
        inner = getattr(reg, "registry", None)
        target = inner if inner is not None and hasattr(inner, "actions") else reg
        return getattr(target, "actions", {})

    if "tools" in kwargs and kwargs["tools"] is not None:
        user_tools = kwargs["tools"]
        try:
            src = _inner_actions(tools)
            dst = _inner_actions(user_tools)
            if dst is not None:
                for name, action in src.items():
                    dst[name] = action
                tools = user_tools
            else:
                raise RuntimeError("无法取得用户 tools 的动作注册表")
        except Exception as e:
            logger.warning(f"合并 follow_memory 到用户 tools 失败，使用自带 tools: {e}")
    else:
        kwargs.pop("tools", None)

    # 7. 创建 Agent
    agent_kwargs = {
        "task": task,
        "llm": llm,
        "tools": tools,
        "register_new_step_callback": step_cb,
        "register_done_callback": done_cb,
    }

    if system_message:
        agent_kwargs["extend_system_message"] = system_message

    # 合并用户参数（覆盖默认值）
    for key, value in kwargs.items():
        if key not in agent_kwargs:
            agent_kwargs[key] = value

    agent = Agent(**agent_kwargs)

    # 8. 在 Agent 创建后保存 browser_session 引用
    # 通过 monkey-patch Agent.run 来获取
    original_run = agent.run

    async def patched_run(*args, **run_kwargs):
        integration._browser_session = agent.browser_session
        return await original_run(*args, **run_kwargs)

    agent.run = patched_run

    # 9. 在每步 LLM 决策前注入当步 DOM 命中的记忆提示（软引导，轨道1）。
    # _prepare_context 返回的即"当步最新 DOM 摘要"，此时机在 LLM(get_next_action) 之前，
    # 与内置 replan/loop nudge 采用同一注入点，因此能真正进入当步 LLM 上下文。
    original_prepare = agent._prepare_context

    async def patched_prepare(step_info=None):
        # 命中即自动设值：在抓 DOM 之前，若记忆中的日期范围控件当前值不对，
        # 直接 input_enter 设成目标窗口，使 LLM 当步看到正确值、不再试错。
        try:
            bs = getattr(agent, "browser_session", None)
            if bs is None:
                logger.debug("[auto_apply] browser_session 为 None，跳过")
            else:
                from .memory.auto_apply import auto_apply_date_ranges

                done = await auto_apply_date_ranges(
                    bs,
                    integration.memory_store,
                    integration.config.element_memory,
                )
                if done:
                    logger.info(f"[auto_apply] 已设日期范围: {done}")
                else:
                    logger.debug("[auto_apply] 无需设值/未命中")
        except Exception as e:
            logger.warning(f"[auto_apply] 执行异常: {e}", exc_info=True)

        summary = await original_prepare(step_info)
        try:
            integration.inject_memory_hints_into_context(agent, summary)
        except Exception:
            pass
        return summary

    agent._prepare_context = patched_prepare

    return agent
