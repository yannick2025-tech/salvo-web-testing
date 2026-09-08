## ADDED Requirements

### Requirement: 模型配置化
系统 SHALL 将模型 provider、base_url、model 名、API KEY 环境变量等全部配置化，写入统一配置文件，不硬编码在脚本中。

#### Scenario: 切换模型只改配置
- **WHEN** 用户在配置文件中将 provider 从 deepseek 改为 qwen
- **THEN** 系统加载对应 provider 的配置与 KEY 环境变量，无需修改任何用例或执行器代码

### Requirement: 统一模型加载
系统 SHALL 提供单一 `llm_factory` 集中加载模型，支持 deepseek 与 Qwen3-Max 各自 SDK，用例脚本中不得出现复用的 if 判断逻辑。

#### Scenario: 按 provider 构造 client
- **WHEN** 调用 `llm_factory.create_llm(cfg)`
- **THEN** 系统根据 `provider` 从注册表选择对应 client 构造函数，读取其 KEY 环境变量并返回 browser-use 可用的 LLM 对象

#### Scenario: 未知 provider 报错
- **WHEN** 配置中的 provider 不在注册表中
- **THEN** 系统抛出明确错误，指出支持的 provider 列表
