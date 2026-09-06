## ADDED Requirements

### Requirement: 记忆按页面拆分与索引
系统 SHALL 将元素记忆从单文件拆分为按页面/模块的多个 JSON 文件，并提供索引文件记录「文件 → url_pattern」映射。

#### Scenario: 读取多文件记忆
- **WHEN** 系统加载记忆
- **THEN** 系统通过索引定位对应页面/模块的记忆文件并读取，而非读取单个大文件

#### Scenario: 兼容旧单文件
- **WHEN** 存在旧的单文件 elements.json
- **THEN** 系统在迁移期仍能读取旧格式，不因拆分导致既有记忆失效
