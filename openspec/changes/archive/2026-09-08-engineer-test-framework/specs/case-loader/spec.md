## ADDED Requirements

### Requirement: 登录 URL 等项目级配置
系统 SHALL 将登录 URL 等项目级环境信息放入统一配置，测试用例文件中不出现登录 URL。

#### Scenario: 用例不出现登录 URL
- **WHEN** 读取任意测试用例 YAML
- **THEN** 用例内容不包含登录 URL，登录 URL 仅存在于全局配置

### Requirement: YAML 用例加载
系统 SHALL 提供 loader 读取结构化 YAML 用例，步骤字段包括 action、target、locator（可省略）、params。

#### Scenario: 解析结构化步骤
- **WHEN** loader 读取一个 YAML 用例文件
- **THEN** 系统解析出有序的步骤列表，每步含 action、target 及可选 locator、params

#### Scenario: 校验非法用例
- **WHEN** 用例缺失必填字段（如 action 或 target）
- **THEN** 系统在加载阶段报错并指明缺失字段

### Requirement: 结构化步骤转 task
系统 SHALL 将结构化步骤转换为与现有可跑通模式一致的自然语言 task 文本。

#### Scenario: 生成 task 文本
- **WHEN** task_builder 接收步骤列表
- **THEN** 系统生成一段自然语言 task，交由 create_memory_agent 执行，行为与现有脚本一致
