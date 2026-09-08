## Context

第二阶段计量（`PromptUsageProfiler`）得到基线：18 步用例全程 prompt 里 DOM 占 18.5%（未缓存全价大头）、history 占 6.6%（累积）。`browser-use 0.13.10` 的 `Agent` 构造函数已暴露 `max_clickable_elements_length=40000`、`max_history_items=None`、`message_compaction` 三个裁剪参数，但项目当前只透传了 `llm_timeout/step_timeout/max_actions_per_step/max_failures`，未透传 prompt 裁剪参数，导致 DOM 序列化撑满 40000 上限、历史无限累积。

## Goals / Non-Goals

**Goals:**

- 透传并调低 `max_clickable_elements_length` 与 `max_history_items`，降低未缓存全价 prompt。
- 保持成功率 100%，用 profiler 量化前后对比。

**Non-Goals:**

- 不做 DOM 智能裁剪（那是方案 B，需深入 serializer）。
- 不做 `message_compaction` 调优（它触发额外的 LLM 压缩调用，净收益需单独评估）。
- 不调 `viewport_threshold`（透传路径在 browser session/DomService 层，本次不涉及）。

## Decisions

### 决策 1：只透传 `max_clickable_elements_length` + `max_history_items`

这两个是「零额外成本」的截断参数（纯本地截断，不触发额外 LLM 调用）。`message_compaction` 会额外调一次 LLM 做摘要，本身消耗 token，净收益不明，暂不纳入。

- **替代（含 message_compaction）**：净收益需评估，留待后续 change。

### 决策 2：`max_clickable_elements_length = 15000`

基线 DOM 单步字符数分布：峰值 22,260（step 15-17 城市级联 + 站点列表 1171 条）、中段 13k-14k（step 8-12 订单列表 204 条）、其余 < 10k。

- 取 15000：截断峰值步骤（22k→15k，单步省约 7k），保留中段 13k-14k 与其余步骤（不受影响），是「截峰值、保主体」的平衡点。
- **替代 10000**：会连中段 13k-14k 一起截，可能丢掉订单列表的「查询」按钮等关键元素，失败风险高。
- **替代 20000**：几乎无效果（只有 22k 峰值被轻微截断）。

### 决策 3：`max_history_items = 10`

browser-use 语义：超过上限时「保留首步 + 最近 `max_history_items-1` 步 + 省略提示」，即 10 时保留首步 + 最近 9 步。18 步用例在中后段开始省略中间历史，显著压缩累积项。

- browser-use 要求 `max_history_items > 5`，10 是「保留足够近期上下文 + 有效压缩」的平衡。
- **替代 15**：压缩有限；**替代 6**：可能丢失跨步骤的关键上下文（如登录态记忆）。

### 决策 4：透传路径 = `RunnerConfig` 加字段 → `runner.py` 透传

`create_memory_agent` 已通过 `**kwargs` 把未知参数透传给 `Agent`，因此**无需改 `integration.py`**，只需在 `RunnerConfig` 加字段、`runner.py` 传入。

- **替代（硬编码在 create_memory_agent）**：配置应外置，不采纳。

## Risks / Trade-offs

- **[DOM 截断丢关键元素 → 任务失败] → 缓解**：取 15000（仅截峰值），跑同一用例回归验证成功率须保持 100%；若不达标，梯度回调（如 18000）。
- **[历史截断丢跨步上下文 → 后续步骤误操作] → 缓解**：max_history_items=10 保留首步 + 最近 9 步，关键近期上下文仍在；回归验证。
- **[参数调低后 DOM 序列化 `(truncated)` 提示可能误导 LLM] → 缓解**：browser-use 截断时会追加 `(truncated to N characters)` 提示，LLM 已知晓；验证成功率。

## Migration Plan

- 纯配置 + 透传改动，无数据迁移、无破坏性变更。
- 回滚：把 `config.yaml` 的两个参数恢复默认值（`max_clickable_elements_length: 40000`、删除 `max_history_items`）即可。

## Open Questions

- 15000 / 10 是否最优：需跑对比后按 profiler 数据与成功率梯度微调。
- 是否在验证通过后，把 `message_compaction` 作为后续 change 评估。

## 实验结果（2026-09-08）：失败，已回滚

按 `max_clickable_elements_length=15000`、`max_history_items=10` 跑同一用例，结果**适得其反**：

| 指标 | 基线 | 方案 A | 变化 |
|------|------|--------|------|
| invocations | 18 | 40 | +122% |
| total_prompt_tokens | 241,930 | 574,806 | +138% |
| total_tokens | 257,662 | 610,815 | +137% |
| 成功率 | 2/2 成功 | 用例2失败 | 下降 |

**失败根因**：

1. `max_clickable_elements_length=15000` 把站点列表页的 DOM 从峰值 22,260 chars 截到 15,376，**城市级联面板的关键元素（江苏省 hover 目标、南京市复选框）被截到上限之外**，LLM 看不到、定位失败。
2. `max_history_items=10` 截断历史，LLM 丢失前面步骤的上下文，在站点列表页**反复试错 23 步**（step 19→41）仍无法完成城市级联选择。
3. 单步 prompt 虽变小，但调用次数翻倍多，每次重发 system+tools 固定开销，**省下的单步 token 被更多重试完全抵消并反超 2.4 倍**。

**结论**：「简单截断」路线走不通——截断 DOM 丢关键元素、截断历史丢上下文，都导致重试暴涨。这**论证了方案 B（DOM 智能裁剪）的必要性**：必须智能决定保留哪些元素（视口内优先、当前步骤相关控件、级联面板展开态），历史也要保留关键节点而非只留最近 N 步。

**处置**：代码改动已回滚（`git checkout` config.yaml / app/config.py / app/runner.py，删除 tests/test_config.py）。本 change 作为实验记录存档。
