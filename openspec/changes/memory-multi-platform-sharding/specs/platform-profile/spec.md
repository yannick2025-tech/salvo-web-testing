## ADDED Requirements

### Requirement: 平台注册表
系统 SHALL 支持在统一配置中声明多个管理平台，每个平台包含唯一语义别名、域名（host）与登录 URL。系统 SHALL 通过精确匹配当前浏览器 URL 的 host 来确定所属平台。

#### Scenario: 按 host 匹配平台
- **WHEN** 当前页面 URL 的 host 命中某平台的 `host` 字段
- **THEN** 系统确定该平台，并使用其别名与登录 URL

#### Scenario: 未知 host 回退
- **WHEN** 当前页面 URL 的 host 未命中任何平台
- **THEN** 系统使用默认平台配置或报错提示，而非静默误路由

### Requirement: 用例按平台组织
系统 SHALL 支持将测试用例按平台分目录组织（一个平台对应一个用例组），并在执行时根据平台注入对应的登录 URL。

#### Scenario: 按平台目录加载用例
- **WHEN** 执行某平台的用例组
- **THEN** 系统从该平台的用例目录加载用例，并注入该平台的登录 URL，用例 YAML 中不出现 URL

#### Scenario: 登录 URL 下移到平台级
- **WHEN** 用例中的 goto 步骤未指定 URL
- **THEN** 系统使用当前平台的登录 URL，而非项目级单一 URL
