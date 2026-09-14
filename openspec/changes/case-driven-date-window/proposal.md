## Why

当前 `auto_apply` 把日期范围控件的目标值硬编码为全局配置的「过去 N 天不含今天」窗口（`date_range_days_back: 10`），完全无视用例的实际需求。随着用例大规模化，日期范围需求是多样且随用例而变的：有的是「前 10 天（不含今天）」，有的是「某一天」，有的是「7 天」，有的是固定区间（如 2026 年 8 月）。这个错位已造成实际失败：franchisee 的「结算记录查询」用例需要固定日期 `2026-08-01 ~ 2026-08-31`，却被 auto_apply 每步反复覆盖回 `2026-09-04 ~ 2026-09-13`，导致 LLM 陷入 20 步试错、两次 120s 超时、最终用例失败。

## What Changes

- **日期值来源由「全局配置」改为「用例步骤声明」**：日期窗口不再是全局单一值，而是每个用例自行声明（固定日期或相对窗口）。
- **用例 YAML 新增 `set_date_range` 动作**：显式承载「日期范围」语义，支持相对窗口表达（如 `days_back`/`include_today`）；`input` 步骤继续承载固定字面日期值（如 `2026-08-01 00:00:00`）。
- **auto_apply 职责收窄**：`auto_apply_date_ranges` 不再自行调用 `compute_date_window` 计算窗口，改为接收「用例声明的目标窗口」作为入参，用该目标值 + 记忆里的设值方式去确定性设值；用例未声明日期目标时跳过设值，避免误伤。
- **记忆职责保持**：记忆仍只存「这是日期范围控件（`el-range-input`）+ 设值方式（原生 setter + input 事件 + Enter）」，不存日期值（现有记忆结构已符合，无需改）。
- **`config.yaml` 的 `date_range_days_back` 语义调整**：退化为「用例未声明日期目标时的可选默认值」，不再作为唯一值来源。

## Capabilities

### New Capabilities

- `date-range-apply`: 日期范围控件的确定性自动设值能力——目标值由用例步骤声明驱动（固定日期或相对窗口），记忆仅提供「控件定位 + 设值方式」，auto_apply 不自行决定值。

### Modified Capabilities

（无。既有 `memory-sharding` 的 spec 仅描述按平台/页面分片，不涉及日期值语义，本次不改变其 spec 级行为。）

## Impact

- **受影响现有代码**：
  - `browser_use_ext/memory/auto_apply.py`（`auto_apply_date_ranges` 去全局窗口计算，改为接收 `target_window` 参数）
  - `browser_use_ext/integration.py`（`patched_prepare` 传入用例日期目标，无目标时跳过）
  - `app/task_builder.py`（新增 `set_date_range` 步骤文本化；新增从步骤提取「日期目标」的辅助函数）
  - `app/case_loader.py`（`ALLOWED_ACTIONS` 增加 `set_date_range`）
  - `app/runner.py`（`_run_suite` 提取用例日期目标并传给 `create_memory_agent`）
  - `config.yaml`（`date_range_days_back` 注释与语义调整）
  - 用例 YAML：`cases/manhattan/smoke.yaml`（相对窗口改用 `set_date_range`）、`cases/franchisee/smoke.yaml`（固定日期保持不变）
- **依赖新增**：无（复用现有 pydantic/pyyaml/asyncio）。
- **风险**：
  - 用例未声明日期目标时，auto_apply 必须跳过设值，避免对无关页面日期控件误设；需在 `auto_apply_date_ranges` 增加 `target_window is None` 早退。
  - 需回归验证两类用例：manhattan「充电订单查询」（相对窗口 `days_back=10`）与 franchisee「结算记录查询」（固定 2026-08），确保二者各自得到正确日期、互不干扰。
