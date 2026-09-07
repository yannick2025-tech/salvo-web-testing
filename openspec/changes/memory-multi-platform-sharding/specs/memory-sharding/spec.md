## MODIFIED Requirements

### Requirement: 记忆按页面拆分与索引
系统 SHALL 将元素记忆从单文件拆分为多个 JSON 文件，并按「平台（host）+ URL path 第一段」两级定位：平台由当前 URL 的 host 经平台注册表映射，分片文件由 URL path 第一段映射（如 `/station` 映射到 `station.json`）。程序侧根据当前页面 URL 自动路由到对应分片，LLM 无需感知文件结构。

#### Scenario: 读取多文件记忆
- **WHEN** 系统加载或查询记忆
- **THEN** 系统根据当前 URL 的 host 定位平台目录，再根据 URL path 第一段定位分片文件并读取，而非读取单个大文件

#### Scenario: 兼容旧单文件
- **WHEN** 存在旧的单文件 elements.json 且平台分片目录尚未建立
- **THEN** 系统在迁移期仍能读取旧格式，不因拆分导致既有记忆失效

## ADDED Requirements

### Requirement: 按 URL 自动路由分片
系统 SHALL 在写入与查询记忆时，根据当前页面 URL 自动确定目标分片，路由键为「host → 平台目录」与「URL path 第一段 → 分片文件」。

#### Scenario: 写入路由到对应平台分片
- **WHEN** learner 学习到一条记忆，其 context.url_pattern 的 host 为 `example-platform.com` 且 path 第一段为 `order`
- **THEN** 系统将该记忆写入 `memory/<platform>/order.json` 分片

#### Scenario: 查询路由到对应分片
- **WHEN** 当前页面 URL 为 `https://example-platform.com/station/site/list`
- **THEN** 系统仅在 `memory/<platform>/station.json` 分片内匹配记忆，而非扫描全部分片

### Requirement: 公共记忆分片
系统 SHALL 为不属于任何一级菜单的页面（如登录页、跨菜单通用控件）提供公共记忆分片。

#### Scenario: 登录页记忆落入公共分片
- **WHEN** 记忆的 URL path 无法解析出稳定的一级菜单段（如登录页 `/Login`）
- **THEN** 系统将该记忆写入对应平台的 `_common.json` 公共分片

### Requirement: 跨菜单用例自动切换分片
系统 SHALL 支持单个用例跨越多个一级菜单，通过每步的 URL 变化自动切换所查询的分片，LLM 无需感知分片切换。

#### Scenario: 跨菜单步骤命中不同分片
- **WHEN** 一个用例先后访问 `/order/...` 与 `/station/...` 两个页面
- **THEN** 系统分别在 `order` 与 `station` 分片内匹配记忆，无需 LLM 指定文件
