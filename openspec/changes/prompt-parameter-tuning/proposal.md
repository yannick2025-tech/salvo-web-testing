## Why

第二阶段报告（`docs/issues/prompt-token-breakdown.md`）用计量数据确认：prompt 构成中，**DOM（18.5%）与 history（6.6%）是「未缓存、全价计费」部分的大头**，是降费用的正确靶心。而 `browser-use 0.13.10` 已经内置了对应的裁剪参数——`max_clickable_elements_length`（DOM 序列化硬上限，默认 40000 字符）与 `max_history_items`（历史消息保留条数，默认 None=无限累积），但本项目**尚未透传、也未调低**，导致大 DOM 场景（站点列表 1171 条）DOM 序列化撑满上限、18 步用例历史一路累积到结束。本 change 透传并调低这些参数，是 prompt 优化的第一步（快赢、低风险、无需改 browser-use 源码）。

## What Changes

- `config.yaml` 的 `runner` 段新增两个可调参数：`max_clickable_elements_length`、`max_history_items`。
- `app/config.py` 的 `RunnerConfig` 新增对应字段（含默认值）。
- `app/runner.py` 把这两个参数透传给 `create_memory_agent`（进而透传给 browser-use `Agent`）。
- 调低默认值（相对 browser-use 内置默认）：
  - `max_clickable_elements_length`：40000 → **15000**（裁剪 DOM 序列化硬上限）
  - `max_history_items`：None（无限）→ **10**（仅保留最近 10 步历史 + 首步）

## Capabilities

### New Capabilities

- `prompt-budget-tuning`: prompt 预算调优——通过透传并调低 browser-use 的 `max_clickable_elements_length`（DOM 序列化上限）与 `max_history_items`（历史保留条数），降低单次运行 prompt 中未缓存、全价计费的部分。

### Modified Capabilities

<!-- 本次为纯新增能力，不改动现有 capability 的 spec 级需求。 -->

## Impact

- **受影响现有代码**：
  - `app/config.py`（`RunnerConfig` 新增 2 字段）
  - `config.yaml`（`runner` 段新增 2 项）
  - `app/runner.py`（透传 2 参数）
- **依赖新增**：无（复用 browser-use 现有参数）。
- **风险**：`max_clickable_elements_length` 调低属于「截断」而非「智能选择」，可能丢掉当前步骤需要但恰好在截断线外的元素，导致任务失败；需跑同一用例回归验证成功率（须保持 100%）。
- **验证方式**：复用 `PromptUsageProfiler` 对比调参前后的六部分占比，并核对成功率。
