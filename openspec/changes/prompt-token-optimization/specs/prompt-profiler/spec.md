## ADDED Requirements

### Requirement: 计量 prompt 各部分占比

系统 SHALL 在每次 LLM 调用时，将 prompt 拆分为「系统提示、工具定义、任务+agent 状态、历史消息、浏览器状态（DOM）、上下文注入」六个部分，分别记录字符数与估算 token（字符数 ÷ 4）。

#### Scenario: 单步计量六部分

- **WHEN** Agent 执行一步 LLM 调用并完成 state message 组装
- **THEN** 记录该步六个部分的字符数与估算 token

#### Scenario: 固定开销仅计一次

- **WHEN** 系统提示与工具定义在整次运行期间保持不变
- **THEN** 该两部分仅计量一次，不随步数重复累加

#### Scenario: DOM 与历史单列

- **WHEN** state message 同时包含 `<agent_history>` 与 `<browser_state>` 块
- **THEN** 历史消息与浏览器状态（含 DOM 主体）分别作为独立列计量，不合并

### Requirement: 输出汇总报告

系统 SHALL 在每次用例运行结束时输出一份汇总报告，包含六部分的合计字符数、估算 token 及占比。

#### Scenario: 运行结束输出汇总

- **WHEN** 一次用例运行结束
- **THEN** 输出六部分合计、估算 token 与占比的汇总报告

#### Scenario: 每步明细可查

- **WHEN** 用户需要定位某一步的 prompt 构成
- **THEN** 报告提供每步六部分的明细数据

### Requirement: 计量不改变执行行为

计量 SHALL 为纯观测：不修改任何 prompt 内容、不改变执行逻辑、不影响任务成功率；计量 hook 抛出的任何异常 SHALL 被捕获并忽略，不影响主流程。

#### Scenario: hook 异常不影响执行

- **WHEN** 计量 hook 在运行期间抛出异常
- **THEN** 捕获并忽略该异常，Agent 继续正常执行

#### Scenario: 关闭或解析失败时降级

- **WHEN** state message 非纯文本（如含截图）或无法解析某块
- **THEN** 跳过该步计量或按整块降级计数，不报错中断

### Requirement: 计量可开关

计量 SHALL 受配置开关控制，关闭时不挂载任何 hook，运行无计量开销。

#### Scenario: 关闭计量

- **WHEN** 配置 `profiling.enabled=false`
- **THEN** 不挂载计量 hook，运行行为与未引入计量前完全一致
