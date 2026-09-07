# Prompt Token 优化设计

> 日期：2026-09-07
> 状态：阶段 1（计量）待实施，阶段 2-4 待计量数据后细化

## 1. 背景与目标

A/B 测试（`docs/issues/qwen3.7-max-memory-vs-no-memory.md`）确认：单次运行中 **prompt 占 total token 的 93.5%~95.4%**，completion 仅占约 5%。因此降本的正确杠杆是 prompt，而非记忆开关或 completion。

**目标**：在不降低成功率（当前有记忆 100%）的前提下，把单次运行的 prompt token 显著压缩。

## 2. 现状：prompt 的构成

基于 `browser-use 0.13.10` 源码，每次 LLM 调用的 prompt 由以下部分组成：

| 部分 | 来源 | 性质 | 可优化性 |
|------|------|------|---------|
| 系统提示词 | `system_prompt.md`（271 行规则）+ 记忆规则扩展 | 固定 | 低（改影响行为） |
| 工具定义 | ~20 个工具的 JSON schema | 固定 | 中（删不必要工具） |
| 任务 + agent 状态 | `<user_request>` + `<agent_state>` | 基本固定 | 低 |
| 历史消息 | `<agent_history>` 每步累积 | 累积 | **高** |
| 浏览器状态（DOM） | `<browser_state>` 内 `Interactive elements` | 动态大头 | **高** |
| 上下文注入 | 记忆命中提示、loop nudge 等 | 小 | 低 |

**关键根因**（源码确认）：

1. `max_clickable_elements_length = 40000`（DOM 序列化硬上限，约 1 万 token/步）——项目未透传、未调低。
2. `max_history_items = None`（历史无限累积）+ 消息压缩 `compact_every_n_steps = 25`——18 步用例永不触发压缩，历史一路涨到结束。
3. `viewport_threshold = 1000px`——视口外 1000px 元素也算「可见」，大页面额外多列数百元素。

## 3. 整体方案（A+B+C 融合，分阶段）

按「先测量 → 再优化 → 逐步融合」推进，避免拍脑袋：

- **阶段 1（当前）**：添加 prompt 计量，拿到各部分的精确占比基线。
- **阶段 2（方案 A）**：透传并调低 browser-use 已有裁剪参数（快赢）。
- **阶段 3（方案 B）**：DOM 序列化智能裁剪（治本，收益最大）。
- **阶段 4（方案 C）**：系统提示/工具精简 + prompt 缓存（固定开销瘦身）。

阶段 2-4 的具体参数与实现，待阶段 1 数据出来后细化。

## 4. 阶段 1：Prompt 计量

### 4.1 目标

量化每次 LLM 调用的 prompt 六部分（系统提示 / 工具 / 任务+状态 / 历史 / DOM / 上下文）的字符数与估算 token，回答「token 到底花在哪」，为后续优化定基线、做前后对比。

### 4.2 测量维度

| 维度 | 获取方式 |
|------|---------|
| 系统提示词 | `message_manager.state.history.system_message.content` 长度（测一次，固定） |
| 工具定义 | `agent.ActionModel.model_json_schema()` 序列化长度（测一次，近似） |
| 任务 + agent 状态 | 解析 state message 的 `<user_request>` + `<agent_state>` 块 |
| 历史消息 | 解析 state message 的 `<agent_history>` 块 |
| 浏览器状态（DOM） | 解析 state message 的 `<browser_state>` 块，其中 `Interactive elements...:` 之后为 DOM 主体 |
| 上下文注入 | `message_manager.state.history.context_messages` 各 content 长度 |

### 4.3 实现方式

新增 `browser_use_ext/prompt_profiler.py`，提供 `PromptUsageProfiler`：

1. `attach(agent)`：在 `create_memory_agent` 创建 Agent 后调用。
   - 测一次系统提示词、工具定义（固定开销）。
   - monkey-patch `message_manager.create_state_messages`：每次调用后解析 `last_state_message_text`，拆分记录各块字符数。
2. 每步记录一条统计，`done_callback` 时打印汇总表格。
3. token 估算：`字符数 ÷ 4`（英文/代码为主），明确标注为估算值——我们只关心**占比**，不追求绝对值精确。

### 4.4 输出格式（示例）

```
===== Prompt Usage Profile =====
step  system  tools  task+state  history  browser_state(DOM)  context
1     3.2k    2.1k   0.8k        0.5k     6.1k                0.2k
...
SUM   3.2k    2.1k   0.8k        9.4k     88.3k               1.1k   (估算 token)
```

### 4.5 非功能约束

- **纯观测**：不改任何 prompt 内容、不改执行逻辑、不影响成功率。
- **零侵入**：不修改 `.venv` 里的 browser-use 源码，全部通过 monkey-patch 在项目层实现。
- **可开关**：受 `config.yaml` 一个开关控制，默认开启（阶段 1 需要），优化完成后可关。

## 5. 阶段 2-4 概要

### 5.1 阶段 2（方案 A：参数调优）

在 `create_memory_agent` / `config.yaml` 透传并调低：
- `max_clickable_elements_length`：40000 → 15000~20000
- `max_history_items`：None → 8~10
- `message_compaction`：`compact_every_n_steps` 25 → 8，`trigger_char_count` → 20000
- `viewport_threshold`：1000 → 300~500

风险：DOM 是「截断」而非「智能选择」，可能丢关键元素，需回归验证成功率。

### 5.2 阶段 3（方案 B：DOM 智能裁剪）

针对大表格/大列表页面做领域化过滤，hook `DOMTreeSerializer`：
- 列表/表格只保留前 N 条 + 「共 X 条」提示
- 结合用例步骤预判本步操作目标，只保留相关控件

收益最大（DOM 有望砍 70%+），但改动大、启发式可能误判。

### 5.3 阶段 4（方案 C：固定开销瘦身）

- 精简 `system_prompt.md`（或 `override_system_message` 替换）
- 移除本用例用不到的工具
- 确认 DashScope 是否支持 prompt 缓存，让系统提示 + 工具前缀只计费一次

## 6. 验证

- 阶段 1：跑一次现有用例，输出计量报告，与 A/B 测试的 total prompt（~25 万）交叉验证（各块之和 ≈ 总 prompt）。
- 阶段 2-4：每次改动前后跑同一用例，对比计量报告 + 成功率（须保持 100%）。
