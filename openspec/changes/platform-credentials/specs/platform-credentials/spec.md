## ADDED Requirements

### Requirement: 平台声明账号密码

系统 SHALL 允许每个平台在 `config.yaml` 的 `platforms.<alias>` 中声明 `account` 与 `password` 字段，且 SHALL 支持用 `${VAR}` 占位符从环境变量注入。

#### Scenario: 平台声明账号密码占位符

- **WHEN** `platforms.<alias>` 含 `account: ${MANHATTAN_ACCOUNT}` 与 `password: ${MANHATTAN_PASSWORD}`
- **THEN** 加载配置后，该平台的 account/password 分别为对应环境变量值

### Requirement: 用例使用通用凭据占位符

用例 YAML SHALL 使用 `${ACCOUNT}` 与 `${PASSWORD}` 通用占位符引用登录凭据，而无需绑定具体平台前缀。

#### Scenario: 用例引用通用凭据

- **WHEN** 用例步骤的 `params.value` 为 `${ACCOUNT}` 或 `${PASSWORD}`
- **THEN** 运行时按该用例所属平台注入对应账号密码

### Requirement: 按平台注入凭据

`load_suite` SHALL 接收 `account` 与 `password` 参数，并在加载用例时把 `${ACCOUNT}` / `${PASSWORD}` 替换为传入值；未传时 MUST 保留原占位符。

#### Scenario: 注入当前平台凭据

- **WHEN** 以 `account="manhattan账号"`、`password="manhattan密码"` 调用 `load_suite`
- **THEN** 加载结果中 `${ACCOUNT}` 被替换为 manhattan账号、`${PASSWORD}` 被替换为 manhattan密码

#### Scenario: 未提供凭据时保留占位符

- **WHEN** 以空 account/password 调用 `load_suite`
- **THEN** `${ACCOUNT}` / `${PASSWORD}` 原样保留（不崩溃）

### Requirement: 多平台凭据隔离

系统 MUST 按用例所属平台注入凭据，不同平台的用例 MUST 各自使用各自的账号密码，且注入 MUST 不依赖任何全局可变状态（每个 suite 使用局部参数）。

#### Scenario: 不同平台用例各用各的账号

- **WHEN** manhattan 用例与 owner 用例分别加载
- **THEN** manhattan 用例注入 manhattan 账号，owner 用例注入 owner 账号，互不影响
