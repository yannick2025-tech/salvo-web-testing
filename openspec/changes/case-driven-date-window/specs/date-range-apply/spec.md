## ADDED Requirements

### Requirement: 日期目标由用例声明驱动

日期范围控件的目标值 SHALL 由测试用例的 `set_date_range` 步骤声明决定，而非由全局配置硬编码。系统 MUST 支持两类声明：固定日期（`start`/`end` 字面值）与相对窗口（`days_back`/`include_today`，如「前 N 天不含今天」）。记忆 SHALL 仅提供「控件定位 + 设值方式」，不得承载具体日期值。

#### Scenario: 用例声明固定日期

- **WHEN** 用例步骤 `set_date_range` 声明 `start: "2026-08-01 00:00:00"` 且 `end: "2026-08-31 23:59:59"`
- **THEN** 系统将该固定区间作为该日期控件的目标值

#### Scenario: 用例声明相对窗口

- **WHEN** 用例步骤 `set_date_range` 声明 `days_back: 10` 且 `include_today: false`
- **THEN** 系统运行时动态计算目标窗口为「今天往前 10 天 ~ 昨天」，而非使用全局单一值

### Requirement: set_date_range 动作解析

系统 SHALL 支持 `set_date_range` 动作，其 `params` MUST 能表达相对窗口（`days_back`、`include_today`）与固定区间（`start`、`end`）。该动作 SHALL 被 `case_loader` 识别为合法 action，并被 `task_builder` 转成自然语言 task 文本。

#### Scenario: 解析相对窗口参数

- **WHEN** 用例包含 `set_date_range` 且 `params` 为 `{ days_back: 7, include_today: false }`
- **THEN** 系统解析出目标窗口「今天往前 7 天 ~ 昨天」，并生成对应 task 文本

#### Scenario: 解析固定区间参数

- **WHEN** 用例包含 `set_date_range` 且 `params` 为 `{ start: "2026-08-01 00:00:00", end: "2026-08-31 23:59:59" }`
- **THEN** 系统解析出固定目标区间 `2026-08-01 ~ 2026-08-31`

### Requirement: auto_apply 按用例目标确定性设值

`auto_apply` SHALL 接收「用例声明的目标窗口」作为入参，用该目标值结合记忆里的设值方式，在每步抓取 DOM 之前对命中的日期范围控件做确定性设值。auto_apply MUST NOT 自行调用全局窗口计算来决定值。

#### Scenario: 用用例目标值设值

- **WHEN** 当前用例声明了目标窗口 `2026-08-01 ~ 2026-08-31`，且页面存在匹配的日期范围控件、当前值不等于目标值
- **THEN** auto_apply 使用该目标窗口设值，使 LLM 当步看到的 DOM 即为正确日期

#### Scenario: 已是目标值则幂等跳过

- **WHEN** 页面日期范围控件当前值已等于用例目标窗口
- **THEN** auto_apply 不重复设值，直接跳过

### Requirement: 用例未声明日期时不干预

当用例未声明任何日期目标时，auto_apply SHALL 跳过日期范围控件的设值，不得使用任何默认窗口覆盖页面现有值。

#### Scenario: 无日期目标跳过设值

- **WHEN** 当前用例不含 `set_date_range` 或带日期值的 `input` 步骤
- **THEN** auto_apply 不对页面上的日期范围控件做任何设值

### Requirement: 记忆仅承载定位与设值方式

日期范围控件的记忆条目 SHALL 只记录「控件类型（如 `el-range-input`）与设值方式（原生 setter + input 事件 + Enter）」，MUST NOT 记录具体日期值。日期值 MUST 始终来源于用例步骤。

#### Scenario: 记忆不存日期值

- **WHEN** 系统学习一条日期范围控件记忆
- **THEN** 记忆仅包含控件定位特征与设值方式，不包含任何具体日期字符串
