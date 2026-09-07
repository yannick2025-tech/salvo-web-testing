## Context

`browser-use 0.13.10` 的每次 LLM 调用，prompt 由 `MessageManager` 组装：一个固定系统消息（`system_prompt.md` 271 行 + 记忆规则扩展）+ 一个动态 state 消息（`AgentMessagePrompt.get_user_message()` 拼出 `<user_request>` / `<agent_history>` / `<agent_state>` / `<browser_state>` / `<read_state>` / `<step_info>` 六块）+ 若干 context 消息（记忆命中提示、loop nudge 等）。工具定义由 LLM 层单独序列化传入。

当前 `app/runner.py` 只能拿到 LLM 返回的 `usage`（总 prompt / completion），无法拆分。要定位优化重点，必须在不改 browser-use 源码、不影响执行的前提下，把 prompt 拆到六个部分分别计量。

## Goals / Non-Goals

**Goals:**

- 量化每次 LLM 调用的 prompt 六部分（系统提示、工具定义、任务+状态、历史、DOM、上下文注入）的字符数与估算 token。
- 运行结束时输出汇总报告（per-step 明细 + 合计），与总 prompt token 交叉验证。
- 纯观测：不改 prompt 内容、不改执行逻辑、不影响成功率。

**Non-Goals:**

- 不做任何 prompt 压缩/裁剪（那是后续 change）。
- 不追求 token 绝对精确（不引入 tokenizer），只保证占比准确。
- 不改动 `.venv` 内 browser-use 源码。

## Decisions

### 决策 1：埋点方式 = monkey-patch `MessageManager.create_state_messages`

在 `create_memory_agent` 创建 Agent 后，用 `PromptUsageProfiler.attach(agent)` 对 `agent._message_manager.create_state_messages` 做 monkey-patch，调用后解析 `last_state_message_text`。

- **替代 A（改 browser-use 源码）**：侵入 `.venv`，升级即失效，维护差。放弃。
- **替代 B（用 register_new_step_callback）**：回调拿不到拼好的 state message 文本，粒度不足。放弃。
- **选它的理由**：项目层零侵入、拿到的是「最终拼好」的真实 prompt 文本、try/except 保护下对主流程零影响。

### 决策 2：测量粒度 = 六部分

系统提示、工具定义、任务+agent 状态、历史、DOM、上下文注入，共六列。DOM 是已知大头、历史是已知累积项，二者必须单列；系统提示与工具是固定开销，合并会掩盖「固定开销是否值得瘦身」的判断。

- **替代（更细，DOM 内部再拆 tabs/page_stats）**：收益边际低，先不做。

### 决策 3：token 估算 = 字符数 ÷ 4

本项目 prompt 以英文/代码/XML 为主，`chars/4` 是业界常用估算（browser-use 自身 `MessageCompactionSettings.chars_per_token` 默认也是 4.0）。我们只关心占比与前后对比，不追求绝对 token。

- **替代（tiktoken / DashScope tokenizer）**：引入依赖、tokenizer 与 qwen 实际分词可能不一致，且占比场景不必要。放弃。

### 决策 4：解析方式 = 正则提取 XML 块

从 `last_state_message_text` 用 `<tag>…</tag>` 正则提取各块；DOM 主体 = `<browser_state>` 内 `Interactive elements...:` 之后的部分。

- **替代（访问 `dom_state.llm_representation()`）**：会在计量时重复序列化 DOM，增加耗时且有潜在副作用。放弃。

### 决策 5：开关控制 = `config.yaml` 的 `profiling.enabled`

默认 `true`（阶段 1 需要），优化完成后可置 `false` 关闭计量以消除任何开销。profiler 在 `enabled=false` 时不挂载任何 hook。

## Risks / Trade-offs

- **[DOM 主体解析依赖浏览器状态文本格式] → 缓解**：`Interactive elements` 前缀是 browser-use 稳定输出格式；若未来版本变化，正则取不到时降级为「整个 `<browser_state>` 块」计数，不报错。
- **[monkey-patch 与未来 browser-use 升级不兼容] → 缓解**：hook 全部 try/except 包裹，签名用 `*args, **kwargs` 透传；失效时仅计量缺失，不影响执行。
- **[`use_vision=True` 时 state message 为 list 而非 str] → 缓解**：本项目 `use_vision=False`，`last_state_message_text` 为纯文本；profiler 对非 str 内容直接跳过该步。
- **[字符数估算与实际 token 偏差（中文占比波动）] → 缓解**：报告明确标注「估算」，只作横向对比，不与计费 token 混用。

## Migration Plan

- 纯新增能力 + 一处挂载 + 一处开关，无数据迁移、无破坏性变更。
- 回滚：置 `profiling.enabled=false` 或撤销挂载即可，运行行为完全不变。

## Open Questions

- 暂无。工具定义列通过 `agent.ActionModel.model_json_schema()` 序列化估算，若与真实发送格式偏差过大，可在拿到首份报告后校准为「反推」（总 prompt − 其余五块）。
