## 1. 配置开关

- [x] 1.1 在 `config.yaml` 新增 `profiling` 配置段（`enabled: true`）
- [x] 1.2 在 `app/config.py` 新增 `ProfilingConfig` 模型并挂到 `Config`，含默认值

## 2. 计量器实现

- [x] 2.1 新建 `browser_use_ext/prompt_profiler.py`，实现 `PromptUsageProfiler` 类：monkey-patch `MessageManager.create_state_messages`，每次调用后从 `last_state_message_text` 正则解析出六部分（系统提示 / 工具定义 / 任务+状态 / 历史 / DOM / 上下文注入）的字符数
- [x] 2.2 实现固定开销计量：系统提示词（`system_message.content`）与工具定义（`agent.ActionModel.model_json_schema()` 序列化）各计量一次
- [x] 2.3 实现汇总报告生成：per-step 明细 + 六部分合计 + 估算 token（字符数 ÷ 4）与占比

## 3. 挂载与输出

- [x] 3.1 在 `create_memory_agent` 中按 `profiling.enabled` 开关挂载 profiler（`PromptUsageProfiler.attach(agent)`），并在 `done_callback` 输出汇总报告
- [x] 3.2 所有 hook 用 try/except 包裹，异常不影响主流程；`use_vision=True` 或非纯文本 state message 时跳过该步计量

## 4. 测试与验证

- [x] 4.1 为 `PromptUsageProfiler` 的 XML 块解析与 token 估算逻辑编写单元测试（`tests/test_prompt_profiler.py`）
- [ ] 4.2 跑一次现有用例（`cases/manhattan/login_and_query.yaml`），核对计量报告各块之和与总 prompt token 量级一致，并输出首份基线报告
