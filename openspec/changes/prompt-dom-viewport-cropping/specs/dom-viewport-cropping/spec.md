## ADDED Requirements

### Requirement: 收紧 DOM 视口阈值

系统 SHALL 通过项目层 monkey-patch 把 browser-use `DomService` 的 `viewport_threshold` 从默认 1000 收紧为可配置值（默认 200），使 DOM 序列化仅保留视口内（含少量缓冲）的可交互元素。

#### Scenario: 阈值生效

- **WHEN** 创建 Agent 并运行用例
- **THEN** `DomService` 实例的 `viewport_threshold` 为配置值（默认 200），DOM 序列化按收紧后的视口过滤元素

#### Scenario: 不侵入 browser-use 源码

- **WHEN** 应用该 patch
- **THEN** 仅通过 monkey-patch 在项目层生效，`.venv` 内 browser-use 源码不被修改

### Requirement: 阈值可配置

系统 SHALL 支持通过配置指定 `viewport_threshold`，并在创建 Agent 时透传；未指定时用默认值 200。

#### Scenario: 配置生效

- **WHEN** `config.yaml` 中设置 `runner.viewport_threshold`
- **THEN** 该值被加载并透传，patch 按该值收紧视口

#### Scenario: 默认值

- **WHEN** 配置未显式指定该参数
- **THEN** 使用默认值 200

### Requirement: 保持任务成功率

收紧视口阈值 SHALL 不降低任务成功率；回归验证同一用例的成功率 SHALL 保持 100%，且总 token 相对方案 A 之前基线下降或持平。

#### Scenario: 回归验证

- **WHEN** 收紧阈值后运行同一用例
- **THEN** 任务成功，DOM 占比下降，且不出现因关键元素不可见导致的定位失败
