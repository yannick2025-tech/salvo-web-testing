## 1. 用例动作与日期目标提取

- [x] 1.1 `app/case_loader.py` 的 `ALLOWED_ACTIONS` 增加 `set_date_range`
- [x] 1.2 `app/task_builder.py` 新增 `set_date_range` 的 `_step_text` 分支（固定区间与相对窗口两种文本化）
- [x] 1.3 `app/task_builder.py` 新增 `extract_date_target(steps)`，从 `set_date_range` 提取并归一化为 `{start, end}` 绝对日期（相对窗口复用 `compute_date_window`）

## 2. auto_apply 改造

- [x] 2.1 `browser_use_ext/memory/auto_apply.py` 的 `auto_apply_date_ranges` 增加 `target_window=None` 参数，`None` 时早退不干预
- [x] 2.2 用 `target_window` 替代主路径中的 `compute_date_window(cfg)` 结果，保留幂等检查与 `_build_set_js` 逻辑不变

## 3. 传递链路

- [x] 3.1 `browser_use_ext/integration.py` 的 `create_memory_agent` 增加 `date_target` 参数并存入实例属性
- [x] 3.2 `patched_prepare` 把 `date_target` 传入 `auto_apply_date_ranges(..., target_window=...)`
- [x] 3.3 `app/runner.py` 的 `_run_suite` 调用 `extract_date_target(steps)` 并传给 `create_memory_agent`

## 4. 用例 YAML 迁移

- [x] 4.1 `cases/franchisee/smoke.yaml` 的「结算记录查询」把两个 `input`（开始/结束时间）改为 `set_date_range`（固定 `start`/`end`）
- [x] 4.2 `cases/manhattan/smoke.yaml` 的「充电订单查询」新增 `set_date_range`（`days_back: 10, include_today: false`），替换/补充原有日期 `verify`

## 5. 配置与文档

- [x] 5.1 `config.yaml` 调整 `date_range_days_back` / `date_range_include_today` 注释，说明其为 `set_date_range` 缺省默认值
- [x] 5.2 更新 `PROJECT_RULES.md`，说明 `set_date_range` 动作与「日期值由用例驱动」约定

## 6. 测试与回归

- [x] 6.1 新增/更新 `tests/test_auto_apply.py`：覆盖 `target_window=None` 跳过、固定区间设值、相对窗口解析
- [x] 6.2 回归 manhattan「充电订单查询」（相对窗口）与 franchisee「结算记录查询」（固定日期），两者各自得到正确日期
- [x] 6.3 全量 `uv run pytest` 绿（89 passed）
