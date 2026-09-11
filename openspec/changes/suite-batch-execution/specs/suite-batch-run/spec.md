## ADDED Requirements

### Requirement: 套件 YAML 结构（setup + cases）

系统 SHALL 支持在单个 YAML 中用 `setup`（公共前置步骤）与 `cases`（多个用例）描述一个测试套件。`setup` MUST 为可选，`cases` MUST 为非空列表，其中每个用例含 `name` 与 `steps`。

#### Scenario: 定义带登录前置的套件

- **WHEN** YAML 顶层包含 `setup`（登录步骤）与 `cases`（多个用例，各含 name/steps）
- **THEN** 系统将该 YAML 解析为一个套件，包含公共 setup 与多个用例

### Requirement: 向后兼容单用例 YAML

仅含顶层 `steps`（无 `cases`）的旧格式 YAML SHALL 继续可用，系统 MUST 将其视为「setup 为空、cases 仅含该单用例」的套件。

#### Scenario: 旧单用例 YAML 正常运行

- **WHEN** YAML 顶层只有 `steps`
- **THEN** 系统将其解析为单用例套件并正常执行，行为与旧版一致

### Requirement: setup 执行一次、cases 复用会话依次执行

系统 SHALL 在同一个浏览器会话中执行套件：`setup` MUST 只执行一次（登录），随后每个 case MUST 复用同一会话依次执行，不得重复登录。每个用例 MUST 有独立的执行历史与独立的成败判定。

#### Scenario: 登录一次跑多个用例

- **WHEN** 套件含 setup（登录）与 2 个用例
- **THEN** 浏览器会话只登录一次
- **AND** 两个用例在同一会话内依次执行
- **AND** 每个用例产生独立的执行历史与成败判定

### Requirement: setup 失败处理

当 `setup` 执行失败时，系统 SHALL 停止后续所有用例，并在报告中标记「登录失败」，所有用例 SHALL 显示为「未执行」。

#### Scenario: 登录失败停止后续用例

- **WHEN** 套件的 setup（登录）执行失败
- **THEN** 后续用例不执行
- **AND** 报告标记「登录失败」，所有用例显示「未执行」

### Requirement: 批跑输入支持文件/目录/多路径

执行入口 SHALL 支持一次传入文件、目录、或文件与目录的任意组合；目录 MUST 展开为其下所有 `*.yaml`（排序），整体去重后依次执行。

#### Scenario: 传入目录批跑

- **WHEN** 执行入口传入一个用例目录
- **THEN** 系统展开并依次执行该目录下所有 `*.yaml`

#### Scenario: 传入多个文件与目录

- **WHEN** 执行入口同时传入多个文件与多个目录
- **THEN** 系统去重、排序后依次执行所有解析出的套件

### Requirement: 报告聚合多用例

一次运行产生的所有用例 SHALL 聚合为一份报告；报告 MUST 按平台分块，每块下列出该平台的所有用例（各可折叠展开步骤与截图），元信息 MUST 展示总用例数、成功数、失败数与通过率。

#### Scenario: 多个用例聚合为一份报告

- **WHEN** 一次运行执行了多个用例
- **THEN** 生成一份报告，元信息展示总用例/成功/失败/通过率
- **AND** 同一平台的所有用例在同一平台块下列出

### Requirement: setup 不占用例行

登录（`setup`）SHALL 不作为用例行出现在报告用例列表中，报告 MUST 只展示业务用例。

#### Scenario: 报告不展示登录作为用例

- **WHEN** 套件含 setup 与 N 个业务用例
- **THEN** 报告用例列表展示 N 行（不含 setup/登录）
