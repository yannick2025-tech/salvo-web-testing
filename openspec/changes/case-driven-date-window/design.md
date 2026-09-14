## Context

`browser_use_ext` 的 `auto_apply` 机制最初是为解决「browser-use 的 `input` 是追加式打字，无法正确设置 Element UI 日期范围控件」而生：在 Agent 每步抓 DOM 之前，按记忆匹配到日期范围控件（`el-range-input`），若当前值不对就用「原生 value setter + input 事件 + Enter」一次性设对。但其目标值被写死为全局配置的「过去 N 天不含今天」（`auto_apply.py::compute_date_window`），完全无视用例差异。

现有用例中：manhattan「充电订单查询」要「过去 10 天不含今天」；franchisee「结算记录查询」要固定 `2026-08-01 ~ 2026-08-31`。后者被 auto_apply 反复覆盖回 `2026-09-04 ~ 2026-09-13`，导致用例失败、LLM 陷入 20 步试错与两次 120s 超时。根本原因不是 LLM 自述的「Shadow DOM 限制」，而是 auto_apply 越权定了值。

执行链：`runner._run_suite` → `build_steps_task(steps)` 生成自然语言 task → `create_memory_agent(task, ...)` → `integration.patched_prepare` 每次抓 DOM 前调用 `auto_apply_date_ranges(bs, store, cfg)`。一个 agent 对应一个 task（setup 或单个 case），因此「当前用例的日期目标」在 agent 生命周期内是常量。

## Goals / Non-Goals

**Goals:**
- 日期值来源从全局配置改为用例步骤声明，支持任意「前 N 天 / 某一天 / 7 天 / 固定区间」等变体。
- auto_apply 收窄为纯执行器：用「用例目标值 + 记忆设值方式」确定性设值，不再自行决定值。
- 用例未声明日期时，auto_apply 不干预（避免误伤无关页面）。
- 复用现有 `compute_date_window` 作为「相对窗口」解析原语，不重写设值 JS。

**Non-Goals:**
- 不改变记忆结构（记忆已只存控件类型 + 设值方式，符合预期）。
- 不改动 browser-use 内核或 Element UI 设值的 `_build_set_js`。
- 不支持「单个用例内多个不同日期范围控件设不同值」——当前一个用例至多一个日期目标，多目标留待后续按 target 名映射扩展。

## Decisions

### 决策 1：日期目标唯一来源为 `set_date_range` 步骤

引入显式 `set_date_range` 动作作为日期范围的唯一声明入口，`params` 支持两种形态：
- 固定区间：`{ start: "2026-08-01 00:00:00", end: "2026-08-31 23:59:59" }`
- 相对窗口：`{ days_back: 10, include_today: false }`（`days_back` 缺省回退到 `config.element_memory.date_range_days_back`）

普通 `input` 步骤不参与日期目标提取（不再做「target 含『开始/结束时间』」的启发式识别），避免多来源歧义。franchisee 用例从两个 `input` 改成一个 `set_date_range`。

**为何不选「保留 input 启发式识别」**：启发式（关键字匹配「开始/结束」+ 日期正则）脆弱，且需要把两个独立 `input` 合并成 start/end，边界多。统一走 `set_date_range` 语义清晰、单一来源，用例可读性也更好。

### 决策 2：提取时立即归一化为绝对日期

`task_builder` 新增 `extract_date_target(steps) -> DateTarget | None`，其中 `DateTarget` 为 `{ start: str, end: str }`（绝对日期字符串，含时间部分原样保留）。相对窗口在提取时用 `compute_date_window` 立即算成绝对日期——因为「今天」在 agent 生命周期内不变，在 runner 层算一次即可，避免 auto_apply 每步重复计算、也避免跨午夜不一致。

**为何不传「表达式」到 auto_apply 再算**：表达式在每步重算既浪费，又可能在长时间运行跨越午夜时产生不一致。归一化为绝对值后，幂等检查与设值逻辑都更简单。

### 决策 3：传递链路 runner → integration → auto_apply

- `runner._run_suite` 调用 `build_steps_task` 后，再调用 `extract_date_target(steps)` 得到 `date_target`。
- `create_memory_agent` 新增可选参数 `date_target`，透传给 `integration`（存为实例属性，如 `integration.date_target`）。
- `integration.patched_prepare` 把 `integration.date_target` 传给 `auto_apply_date_ranges(..., target_window=...)`。
- 由于一个 agent 一个用例，`date_target` 在 agent 生命周期内不变，闭包捕获即可。

### 决策 4：auto_apply 增加 `target_window` 参数并早退

`auto_apply_date_ranges(browser_session, store, cfg, target_window=None)`：
- `target_window is None` → 直接 `return None`（不干预）。
- 否则用 `target_window` 替代 `compute_date_window(cfg)` 的结果作为 `start, end`，其余逻辑（记忆匹配、`_CHECK_JS` 幂等检查、`_build_set_js`）不变。

`compute_date_window` 保留为公开原语，仅被 `extract_date_target` 的相对窗口分支复用，不再在 auto_apply 主路径中调用。

### 决策 5：`date_range_days_back` 降级为相对窗口默认值

`config.element_memory.date_range_days_back` 不再作为 auto_apply 的唯一值来源，而降级为「`set_date_range` 未显式给 `days_back` 时的默认 `days_back`」。`date_range_include_today` 同理作为默认 `include_today`。

## Risks / Trade-offs

- [用例未声明日期时误设无关页面] → 通过 `target_window is None` 早退规避，并保留 `_is_range_date_control` + URL 匹配双重过滤。
- [manhattan 相对窗口与 franchisee 固定日期互相污染] → 二者分别由各自用例的 `set_date_range` 声明，agent 生命周期内目标恒定，不共享全局窗口。
- [固定日期带时间与相对窗口不带时间的格式不一致] → `DateTarget` 原样保留字面字符串，`_build_set_js` 与幂等检查均按前缀匹配（`vals[i].startswith(target[i])`），对「带时间 / 不带时间」都能正确工作。
- [回归风险：改动影响现有跑通的充电订单用例] → 任务中要求回归 manhattan「充电订单查询」（相对窗口）与 franchisee「结算记录查询」（固定日期）两个用例，均需通过。

## Migration Plan

1. 新增 `set_date_range` 动作与 `extract_date_target`，保持旧路径可用（未声明日期的用例走「不干预」分支，行为等价于修复前的「无命中」）。
2. 更新 franchisee 用例：两个 `input`（开始/结束时间）→ 一个 `set_date_range`（`start`/`end` 固定）。
3. 更新 manhattan 用例：日期相关 `verify` 步骤旁新增 `set_date_range`（`days_back: 10, include_today: false`）。
4. 回归两类用例；无需数据迁移（记忆结构不变）。

## Open Questions

- 单个用例内若未来出现「两个不同日期范围控件要设不同值」，是否需要将 `DateTarget` 升级为「target 名 → 窗口」的映射？（当前明确不支持，后续按需扩展。）
