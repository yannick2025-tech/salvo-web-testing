## Why

当前测试账号是全局环境变量 `TEST_ACCOUNT` / `TEST_PASSWORD`，用例 YAML 里写 `${TEST_ACCOUNT}`。当框架接入多个平台（manhattan、业主管理平台等）且每个平台账号密码不同时，全局账号会冲突——无法让不同平台的用例各自使用各自的登录凭据。

需要把「账号密码」从全局下沉到「平台级配置」：每个平台一套账号密码，用例按自己所属平台注入对应凭据。

## What Changes

- **平台配置扩展**：`config.yaml` 的 `platforms.<alias>` 增加 `account` / `password` 字段（用 `${<前缀>_ACCOUNT}` / `${<前缀>_PASSWORD}` 占位符从环境注入）。
- **env 组织**：`.env` 用「平台前缀」扁平命名，一组平台一套（`MANHATTAN_ACCOUNT` / `MANHATTAN_PASSWORD` / `OWNER_ACCOUNT` / `OWNER_PASSWORD` …），替代全局 `TEST_ACCOUNT`。
- **用例占位符通用化**：用例 YAML 用 `${ACCOUNT}` / `${PASSWORD}` 通用占位符，不再写平台前缀，由运行时按平台注入。
- **加载注入**：`load_suite` 接收 `account` / `password` 参数，加载时把 `${ACCOUNT}` / `${PASSWORD}` 替换为当前平台的凭据；注入走**局部参数传递**，不引入全局状态，保证多平台（含并行）不串。

## Capabilities

### New Capabilities

- `platform-credentials`: 平台级登录凭据——每个平台在 `config.yaml` 中声明自己的账号密码，用例通过通用占位符 `${ACCOUNT}`/`${PASSWORD}` 引用，运行时按用例所属平台局部注入。

### Modified Capabilities

<!-- 仅扩展 config 的 Platform 模型与 case 加载的注入，不修改 element-memory / popup-watchdog / prompt-profiler / suite-batch-run 的 spec 级行为。 -->

## Impact

- **受影响文件**：
  - `app/config.py`：`Platform` 模型加 `account` / `password` 字段。
  - `app/case_loader.py`：`load_suite` 增加 `account` / `password` 参数并做占位符注入。
  - `app/runner.py`：`_run_suite` 从 `config.platform(platform_alias)` 取凭据传给 `load_suite`。
  - `config.yaml` / `.env.example`：platforms 段加账号密码占位、env 加平台前缀账号变量。
  - `cases/manhattan/smoke.yaml`：`${TEST_ACCOUNT}` / `${TEST_PASSWORD}` 改为 `${ACCOUNT}` / `${PASSWORD}`。
- **依赖新增**：无（复用现有 `expand_env_vars` 机制，扩展其支持额外映射）。
- **风险**：低。账号注入为纯局部参数传递，无全局状态；向后兼容（不传 account/password 时 `${ACCOUNT}` 保留原样，等价于旧行为）。
