# Prompt Token 构成细粒度分析报告（第二阶段）

> 日期：2026-09-08
> 模型：qwen3.7-max
> 用例：`cases/manhattan/login_and_query.yaml`（18 步）
> 承接：`qwen3.7-max-memory-vs-no-memory.md`（第一阶段 A/B 测试）

## 1. 背景

第一阶段 A/B 测试确认：prompt 占单次运行 total token 的 **93.5%~95.4%**，是降本的核心杠杆。但当时只有「总 prompt / 总 completion」两个粗粒度数字，无法拆分 prompt 内部构成；「DOM 是 token 绝对大头」是当时**基于观察（站点列表 1171 条）的定性推断**，未经过计量验证。

第二阶段引入 **PromptUsageProfiler**（`openspec/changes/prompt-token-optimization/`），在每次 LLM 调用时把 prompt 拆成六部分计量，用数据回答「token 到底花在哪」，并为后续优化提供可量化的前后对比基线。

## 2. 方法

- 计量器：`browser_use_ext/prompt_profiler.py`，monkey-patch `MessageManager`，纯观测、不影响执行。
- 六部分：系统提示（system）、工具定义（tools）、任务+agent 状态（task+state）、历史消息（history）、浏览器状态/DOM（browser_state）、上下文注入（context）。
- 本次为**无记忆态**（`element_memory.enabled=false`），故 context=0。
- token 估算：字符数 ÷ 4（只用于占比对比，不追求绝对精确）。

## 3. 基线数据（全程累计，18 次 LLM 调用）

| 部分 | 全程 chars | 估算 token | 占比 |
|------|-----------|-----------|------|
| **system（×18）** | 433,566 | 108,392 | **39.1%** |
| **tools（×18）** | 378,720 | 94,680 | **34.1%** |
| browser_state(DOM) | 205,946 | 51,487 | 18.5% |
| history | 72,788 | 18,197 | 6.6% |
| task+state | 19,194 | 4,799 | 1.7% |
| context | 0 | 0 | 0% |
| **TOTAL** | **1,110,214** | **277,554** | 100% |

- 固定开销单次：system=24,087 chars、tools=21,040 chars。
- DOM 主体（`Interactive elements` 部分）= 200,370 chars，占 browser_state 的 97.3%。

### 3.1 真实用量对照

| 指标 | 值 |
|------|-----|
| total_prompt_tokens | 241,930 |
| total_completion_tokens | 15,732 |
| **total_prompt_cached** | **71,808（29.7%）** |
| invocations | 18 |

> 估算总计 277,554 与真实 prompt 241,930 差 14.7%，是 `chars/4` 对中英混合内容的固有估算偏差；占比为相对值，不受影响。

### 3.2 每步动态部分规律

- **history 持续累积**：从 step1 的 132 chars 线性涨到 step18 的 8,267 chars，合计 72,788。
- **DOM 波动明显**：订单列表页（step 8-12）稳定在 13k~14k chars；城市级联面板展开 + 站点列表 1171 条（step 15-17）冲到 22k chars 峰值。

## 4. 对第一阶段推断的修正

第一阶段「**DOM 是 token 绝对大头**」的定性判断被本阶段数据修正：

- **总量层面**：固定开销 `system(39.1%) + tools(34.1%) = 73.2%` 才是最大头，DOM 只占 **18.5%**。
- DOM 的真实身份是「**动态、未缓存、全价计费**部分里的最大头」，而非「总量最大头」。

第一阶段 A/B 测试的其他核心结论（记忆系统价值、成功率、10.6% 开销、prompt 占 95%）均基于真实 usage，**不受影响、保持不变**。

## 5. 计费视角（prompt caching）

真实 `total_prompt_cached = 71,808`（29.7%）说明 DashScope 的 prompt caching 已生效：

- `system + tools` 是**固定前缀**，被缓存命中，计费大幅降低（缓存价远低于全价）；
- `DOM + history` 是**每步变化的动态内容**，无法缓存，按全价计费。

因此「降 token 总量」和「降费用」是两个不同的靶心：

| 目标 | 靶心 |
|------|------|
| 降 token 总量 | system + tools（73%，但有缓存兜底） |
| **降费用** | **DOM（18.5%）+ history（6.6%）**（全价、未缓存） |

## 6. 优化方向（按修正后数据排序）

1. **裁剪 DOM（费用第一杠杆）**：DOM 占未缓存全价部分的大头。方向 = 大表格/大列表只列前 N 条 + 「共 X 条」提示、视口优先（对应 openspec 方案 B）。
2. **压缩 history（费用第二杠杆）**：`max_history_items` 限制累积，18 步用例从无限累积改为保留最近 N 步（对应方案 A）。
3. **精简 system + tools（总量第一杠杆，费用次之）**：`system_prompt.md` 271 行精简、移除本用例用不到的工具。虽已被缓存缓解，但能进一步降低缓存的 base 费用（对应方案 C）。

## 7. 结论

1. 第二阶段用计量数据回答了「token 花在哪」：**总量上 system+tools=73%、DOM=18.5%、history=6.6%**。
2. 修正了第一阶段「DOM 是绝对大头」的定性推断——DOM 是「未缓存全价部分」的最大头，不是总量最大头。
3. 结合 prompt caching，**降费用的正确靶心是 DOM + history**（全价、未缓存），降 token 总量的靶心是 system+tools（但有缓存兜底）。
4. 后续优化将按「裁剪 DOM → 压缩 history → 精简固定开销」推进，并以本报告的六部分占比作为前后对比基线。
