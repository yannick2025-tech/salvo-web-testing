## Why

A/B 测试（`docs/issues/qwen3.7-max-memory-vs-no-memory.md`）确认：单次运行中 prompt 占 total token 的 **93.5%~95.4%**，completion 仅约 5%，因此降本的正确杠杆是 prompt 而非记忆开关或输出。但当前 runner 只打印「总 prompt / 总 completion」两个粗粒度数字，无法回答 prompt 内部各部分（系统提示 / 工具定义 / 任务+状态 / 历史 / DOM / 上下文注入）各占多少，导致优化方向只能靠猜、优化效果无法量化对比。本 change 先补齐「计量」能力，为后续参数调优、DOM 裁剪、固定开销瘦身提供数据基线。

## What Changes

- 新增 **prompt 构成计量能力**：量化每次 LLM 调用的 prompt 六部分（系统提示、工具定义、任务+agent 状态、历史消息、浏览器状态/DOM、上下文注入）的字符数与估算 token。
- 每次运行结束时输出一份汇总报告（含 per-step 明细），回答「token 花在哪」。
- 纯观测性改动：**不修改任何 prompt 内容、不改变执行逻辑、不影响成功率**。
- 通过 `config.yaml` 开关控制，默认开启，优化完成后可关闭。

## Capabilities

### New Capabilities

- `prompt-profiler`: prompt 构成计量——在 Agent 运行时对每次 LLM 调用的 prompt 按六个部分分别统计字符数与估算 token，运行结束输出汇总报告。

### Modified Capabilities

<!-- 本次为纯新增计量能力，不改动现有 capability 的 spec 级需求。 -->

## Impact

- **新增文件**：`browser_use_ext/prompt_profiler.py`（计量器 `PromptUsageProfiler`）。
- **受影响现有代码**：
  - `browser_use_ext/integration.py`（在 `create_memory_agent` 中挂载 profiler，done 时输出报告）。
  - `app/config.py` / `config.yaml`（新增计量开关，如 `profiling.enabled`）。
- **依赖新增**：无（复用现有 `json` / `re` / `logging`，不引入第三方 tokenizer）。
- **技术要点**：全部通过 monkey-patch `MessageManager.create_state_messages` 在项目层实现，**不修改 `.venv` 内 browser-use 源码**；所有 hook 用 try/except 保护，任何异常都不影响主流程。
- **风险**：低（纯观测）；token 为「字符数 ÷ 4」的估算值，只用于占比对比，不追求绝对精确。
