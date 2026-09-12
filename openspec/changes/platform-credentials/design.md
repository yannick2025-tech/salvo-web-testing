## Context

项目用 `${VAR}` 占位符 + `.env` 注入敏感信息（域名、API key、账号密码）。当前账号是全局 `TEST_ACCOUNT` / `TEST_PASSWORD`，用例 YAML 写 `${TEST_ACCOUNT}`。接入多平台（manhattan、业主管理平台…）后，各平台账号密码不同，全局账号无法满足「不同平台的用例各用各的凭据」。

现状约束：敏感信息一律不进版本库（`.env` git-ignored）；`config.yaml` 的 `platforms` 已是「别名 → {host, login_url}」字典结构；`runner` 已能按用例路径 `cases/<alias>/...` 推断平台别名（`_infer_platform`），并在 `_run_suite` 里拿到 `platform_alias`。

## Goals / Non-Goals

**Goals:**

- 每个平台在 `config.yaml` 声明自己的账号密码，用例按所属平台注入对应凭据。
- 用例 YAML 用通用占位符 `${ACCOUNT}` / `${PASSWORD}`，不写死平台前缀。
- 多平台（含未来并行）注入不串，账号映射可追溯、可测试。

**Non-Goals:**

- 不改动登录流程 / 用例结构 / 记忆系统。
- 不做账号的加密存储或外部密钥管理（仍用 `.env` 明文，遵循现有约定）。

## Decisions

### 决策 1：env 组织 = 平台前缀扁平命名（不用 JSON）

`.env` 是扁平 `key=value`，无法原生表达「数组/字典」。用**平台前缀**把嵌套结构扁平化：

```bash
MANHATTAN_ACCOUNT=xxx
MANHATTAN_PASSWORD=xxx
OWNER_ACCOUNT=xxx
OWNER_PASSWORD=xxx
```

- **替代（JSON 单变量）**：`ACCOUNTS='{"manhattan":{...}}'`——转义麻烦、难读、diff 不友好，破坏 `.env` 一行一变量与 CI 注入惯例。放弃。

### 决策 2：账号归属平台配置（platforms 段字段）

`config.yaml` 的 `platforms.<alias>` 增加 `account` / `password`：

```yaml
platforms:
  manhattan:
    host: ${MANHATTAN_HOST}
    login_url: ${MANHATTAN_LOGIN_URL}
    account: ${MANHATTAN_ACCOUNT}
    password: ${MANHATTAN_PASSWORD}
  owner:
    host: ${OWNER_HOST}
    login_url: ${OWNER_LOGIN_URL}
    account: ${OWNER_ACCOUNT}
    password: ${OWNER_PASSWORD}
```

这就是「每个元素是一个字典」的结构——`platforms` 是 dict，每个值是含 host/login_url/account/password 的 dict。

### 决策 3：用例 YAML 用通用占位符 `${ACCOUNT}` / `${PASSWORD}`

用例写 `${ACCOUNT}` / `${PASSWORD}`（不带平台前缀），这样 `cases/manhattan/` 与 `cases/owner/` 可复用同一套写法，账号由运行时按平台注入。

### 决策 4：账号映射链路（用户关键疑问：如何映射正确值、多平台并行如何不搞混）

**用户疑问（记录以备维护）**：「用例 YAML 中 `ACCOUNT` 如何映射到正确值，而不搞混，尤其是多个平台并行跑的时候？」

**答复与结论**：`ACCOUNT` 不靠全局变量映射，而是靠「每个用例自己的平台别名」在加载时**局部注入**，三层链路层层隔离：

```
cases/manhattan/smoke.yaml  ──路径推断──▶ platform_alias="manhattan"
cases/owner/xxx.yaml        ──路径推断──▶ platform_alias="owner"
                                        │
                          config.platform(alias) → { account, password }
                                        │
            load_suite(path, account, password) 内：${ACCOUNT} → platform.account
```

- **平台上下文来源** = 用例文件路径 `cases/<alias>/...` 推断的 `platform_alias`（每个文件独立）；显式 `--platform` 可覆盖。
- **账号注入方式** = `load_suite(path, account="", password="")` 的**局部参数**，加载时只替换当前 suite 的 `${ACCOUNT}` / `${PASSWORD}`。
- **不串的根本保证**：`platform_alias` 是 `_run_suite` 的入参、`account`/`password` 是局部变量，**不存在模块级/类级「当前账号」全局状态**。顺序跑和并行跑（未来 `asyncio.gather` 多个 `_run_suite`）都各自持有自己的参数，互不干扰。

**替代（全局「当前平台/当前账号」状态）**：并发下会被打乱，且难测试。放弃。

### 决策 5：注入实现 = 扩展 `expand_env_vars` 支持额外映射

`expand_env_vars(obj, extra=None)` 增加 `extra` 映射，`${VAR}` 优先从 `extra` 取、回退 `os.environ`。`load_suite` 内部用 `extra={"ACCOUNT": account, "PASSWORD": password}` 完成平台注入，复用现有占位符机制。

## Risks / Trade-offs

- **[`${ACCOUNT}` 未注入（平台未注册）] → 缓解**：保留原样 `${ACCOUNT}`（不崩溃），runner 已有「平台未注册」warning，便于发现配置缺失。
- **[平台别名命名冲突] → 缓解**：`platform_alias` 与 `cases/<alias>` 目录名、`platforms.<alias>` 键一致，现有约定已保证。
- **[账号明文入 `.env`] → 缓解**：`.env` 已 git-ignored，符合项目现状；如需更强安全再引入外部密钥（Non-Goal）。

## Migration Plan

- 纯增量：`Platform` 加两个字段、`load_suite` 加两个参数、`expand_env_vars` 加可选映射；旧用例不改也能跑（`${TEST_ACCOUNT}` 仍走全局 env）。
- 迁移动作：`smoke.yaml` 的 `${TEST_ACCOUNT}` → `${ACCOUNT}`；`.env` 增加 `MANHATTAN_ACCOUNT` / `MANHATTAN_PASSWORD`（可从 `TEST_ACCOUNT` 迁移）。
- 回滚：移除 platform 的 account/password 字段与注入调用即可，行为回到旧全局账号。

## Open Questions

- 暂无阻塞项。后续可考虑：多账号/多环境（staging/prod）选择、账号轮换、密码脱敏展示。
