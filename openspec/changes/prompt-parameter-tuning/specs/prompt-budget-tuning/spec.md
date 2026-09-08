## ADDED Requirements

### Requirement: 配置 DOM 序列化上限

系统 SHALL 支持通过配置指定 `max_clickable_elements_length`（DOM 序列化字符数硬上限），并在创建 Agent 时透传给 browser-use，用于裁剪大 DOM 场景的 prompt。

#### Scenario: 配置生效

- **WHEN** `config.yaml` 中设置 `runner.max_clickable_elements_length`
- **THEN** 该值被加载进 `RunnerConfig` 并透传给 `create_memory_agent`，最终作用于 browser-use `Agent`

#### Scenario: 默认值低于 browser-use 内置默认

- **WHEN** 配置未显式指定该参数
- **THEN** 默认值低于 browser-use 内置的 40000，以降低未缓存 prompt

### Requirement: 配置历史保留条数

系统 SHALL 支持通过配置指定 `max_history_items`（历史消息保留条数），并在创建 Agent 时透传给 browser-use，用于限制历史累积。

#### Scenario: 配置生效

- **WHEN** `config.yaml` 中设置 `runner.max_history_items`
- **THEN** 该值被加载进 `RunnerConfig` 并透传给 `create_memory_agent`，最终作用于 browser-use `Agent`

#### Scenario: 关闭历史截断

- **WHEN** 配置 `runner.max_history_items` 为 null 或不设置
- **THEN** 不限制历史累积，行为与 browser-use 默认一致

### Requirement: 调参不降低成功率

调低上述参数 SHALL 不降低任务成功率；回归验证同一用例的成功率 SHALL 保持 100%。

#### Scenario: 回归验证

- **WHEN** 调低参数后运行同一用例
- **THEN** 任务成功，且 DOM 序列化按新上限截断、历史按新条数保留
