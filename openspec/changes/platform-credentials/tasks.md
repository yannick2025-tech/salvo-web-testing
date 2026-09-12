## 1. 配置模型

- [x] 1.1 在 `app/config.py` 的 `Platform` 模型新增 `account` / `password` 字段（默认空串）
- [x] 1.2 在 `config.yaml` 的 `platforms.<alias>` 加 `account: ${..._ACCOUNT}` / `password: ${..._PASSWORD}` 占位
- [x] 1.3 在 `.env.example` 加平台前缀账号变量示例（`MANHATTAN_ACCOUNT` / `MANHATTAN_PASSWORD` 等）

## 2. 占位符注入

- [x] 2.1 在 `app/config.py` 的 `expand_env_vars` 增加可选 `extra` 映射（`${VAR}` 优先取 extra、回退 os.environ）
- [x] 2.2 在 `app/case_loader.py` 的 `load_suite` 增加 `account` / `password` 参数，加载时用 extra 映射注入 `${ACCOUNT}` / `${PASSWORD}`

## 3. runner 按平台注入

- [x] 3.1 在 `app/runner.py` 的 `_run_suite` 中，从 `config.platform(platform_alias)` 取 account/password 并传给 `load_suite`
- [x] 3.2 迁移 `cases/manhattan/smoke.yaml`：`${TEST_ACCOUNT}` / `${TEST_PASSWORD}` 改为 `${ACCOUNT}` / `${PASSWORD}`

## 4. 测试与验证

- [x] 4.1 `expand_env_vars` extra 映射单元测试（extra 优先、回退 env、缺失保留）
- [x] 4.2 `load_suite` 凭据注入单元测试（注入正确值、未提供保留占位符）
- [x] 4.3 多平台隔离单元测试：两个平台账号不同，各自加载结果互不串
