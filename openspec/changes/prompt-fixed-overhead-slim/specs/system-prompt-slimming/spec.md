## ADDED Requirements

### Requirement: 替换精简版系统提示

系统 SHALL 支持通过 `override_system_message` 替换默认 271 行系统提示为精简版，删除本项目无关章节（file_system、planning、browser_vision、examples），降低 system message 的 token 开销。

#### Scenario: 精简生效

- **WHEN** 启用 system prompt 精简并创建 Agent
- **THEN** system message 使用精简版，字符数下降

#### Scenario: 保留核心规则

- **WHEN** 使用精简版系统提示运行用例
- **THEN** output JSON 格式、action 规则、browser 规则、critical_reminders 等核心规则仍存在，LLM 输出格式正确、任务成功

### Requirement: 精简可配置

系统 SHALL 支持通过配置开关 system prompt 精简；关闭时使用默认完整系统提示。

#### Scenario: 关闭精简

- **WHEN** 配置 system prompt 精简开关为 false
- **THEN** 使用默认完整系统提示，行为与未引入精简前一致

### Requirement: 保持任务成功率

精简系统提示 SHALL 不降低任务成功率；回归验证同一用例成功率 SHALL 保持 100%。

#### Scenario: 回归验证

- **WHEN** 启用精简后运行同一用例
- **THEN** 任务成功，system 定义字符数下降，且无输出格式错误
