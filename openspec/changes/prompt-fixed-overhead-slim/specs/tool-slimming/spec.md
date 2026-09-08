## ADDED Requirements

### Requirement: 排除用不到的工具

系统 SHALL 支持通过配置排除本项目用不到的工具（如 search、upload_file、save_as_pdf、文件操作、find_text、close），在创建 Agent 时以 `Tools(exclude_actions=[...])` 生效，降低 tools 定义的 token 开销。

#### Scenario: 工具排除生效

- **WHEN** 配置了工具排除清单并创建 Agent
- **THEN** 被排除的工具不出现在 LLM 可用的 action 列表中，tools 定义字符数下降

#### Scenario: 保留必需工具

- **WHEN** 排除工具后运行用例
- **THEN** 用例用到的工具（navigate/click/input/wait/scroll/done/evaluate/dropdown 等）仍可用，任务成功

### Requirement: 工具排除可配置

系统 SHALL 支持通过配置指定工具排除清单；未指定时用默认清单（排除 search/upload_file/save_as_pdf/write_file/replace_file/read_file/find_text/close）。

#### Scenario: 默认清单生效

- **WHEN** 配置未显式指定排除清单
- **THEN** 使用默认排除清单

### Requirement: 保持任务成功率

排除工具 SHALL 不降低任务成功率；回归验证同一用例成功率 SHALL 保持 100%。

#### Scenario: 回归验证

- **WHEN** 排除工具后运行同一用例
- **THEN** 任务成功，tools 定义字符数下降
