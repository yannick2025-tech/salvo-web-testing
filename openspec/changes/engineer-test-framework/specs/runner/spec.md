## ADDED Requirements

### Requirement: 统一执行器
系统 SHALL 提供单一 runner 接收用例文件路径，驱动完整测试流程，不动态生成 py 文件。

#### Scenario: 按路径执行用例
- **WHEN** 用户执行 `python -m app.runner cases/<case>.yaml`
- **THEN** 系统依次完成「加载配置 → 建模型 → 加载用例 → 转 task → 装配 agent → 执行」并输出结果

#### Scenario: 定位优先命中记忆
- **WHEN** 用例步骤执行且对应元素定位已存在于记忆中
- **THEN** 系统优先使用记忆中的定位，未命中再回退 LLM 现场定位
