# Prompt 降本优化 · 总索引（Index）

> 更新：2026-09-14
> 目标：降低单次运行 prompt token（实测占 total 的 93.5%~95.4%）
> 模型：qwen3.7-max

## 一、方案总览（Mapping）

| 阶段 | 方案 | 手段 | 结果 | 关键数据 | 状态 |
|---|---|---|---|---|---|
| 阶段 1 | 计量 | `PromptUsageProfiler` 六部分计量 | 摸清构成 | system+tools 73%、DOM 18.5%、history 6.6% | ✅ 落地 |
| 阶段 2 | **方案 A** · 简单截断 | `max_clickable_elements_length=15000` + `max_history_items=10` | ❌ 失败 | invocations 18→40、total **+137%** | 已回滚 |
| 阶段 3 | **方案 B** · 视口裁剪 | `viewport_threshold` 1000→200 | ✅ 成功 | total **-6.2%**（257,662→241,697） | 已落地 |
| 阶段 3 补充 | 表格折叠 | 结构签名折叠重复行 | ❌ 失败 | 误伤导航菜单、破坏翻页 | 已回滚 |
| 阶段 4 | **方案 C1** · 工具精简 | `Tools(exclude_actions=[...])` 排除 8 个工具 | ✅ 成功 | tools **-34.5%**（21,040→13,781） | 已落地 |
| 阶段 4 | **方案 C2** · system 精简 | `override_system_message` 删 4 段冗余 | ✅ 成功 | system **-45.8%**（24,087→13,060） | 已落地 |

## 二、固定开销累计收益（C1 + C2）

| 固定开销（单次 LLM 调用） | 优化前 | 优化后 | 降幅 |
|---|---|---|---|
| system（C2） | 24,087 | 13,060 | -45.8% |
| tools（C1） | 21,040 | 13,781 | -34.5% |
| **合计** | **45,127** | **26,841** | **-40.5%** |

## 三、报告档案映射

| 方案 | 结果报告 | OpenSpec change | 说明 |
|---|---|---|---|
| 阶段 1 计量 | [`prompt-token-breakdown.md`](./prompt-token-breakdown.md) | `prompt-token-optimization` | 六部分占比基线 |
| 方案 A 简单截断 | [`prompt-optimization-experiments.md`](./prompt-optimization-experiments.md) | `prompt-parameter-tuning` | 失败数据 + 根因 |
| 方案 B 视口裁剪 | [`prompt-optimization-experiments.md`](./prompt-optimization-experiments.md) | `prompt-dom-viewport-cropping` | 梯度测试 0/200/1000 |
| 表格折叠 | [`prompt-optimization-experiments.md`](./prompt-optimization-experiments.md) | `prompt-table-collapse` | 误伤根因 |
| 方案 C1 工具精简 | `prompt-fixed-overhead-slim/tasks.md` | `prompt-fixed-overhead-slim` | tools -34.5% |
| **方案 C2 system 精简** | [`prompt-optimization-c2-system-slim.md`](./prompt-optimization-c2-system-slim.md) | `prompt-fixed-overhead-slim` | system -45.8% |

> 总览实验回顾见 [`prompt-optimization-experiments.md`](./prompt-optimization-experiments.md)。

## 四、当前基线

| 项 | 值 |
|---|---|
| 已生效优化 | `viewport_threshold=200`（方案 B）、`tool_exclude`（C1）、`slim_system_prompt`（C2） |
| 固定开销单次 | system 13,060 + tools 13,781 = 26,841 chars |
| 成功率 | 3/3（smoke：登录 / 充电订单 / 站点列表） |

## 五、关键教训（供后续回顾）

1. **简单截断（固定字符数/条数）→ 丢关键元素 → 重试暴涨**：方案 A 截 DOM 到 15000 切掉城市级联关键元素、截历史到 10 丢上下文，token 反涨 2.4 倍。
2. **「结构相同」≠「语义相同」**：表格折叠把导航菜单项也当重复行折叠，破坏翻页。
3. **视口裁剪是唯一安全有效的 DOM 优化**：它「恢复 browser-use 设计意图」而非「新造裁剪规则」。
4. **降本分两个维度**：降 token 总量看 system+tools（有缓存兜底）；降费用看 DOM+history（未缓存全价）。
5. **固定开销精简要「删无用」而非「压缩有用」**：C1 只排除明确用不到的工具、C2 只删依赖已排除工具/已关闭能力的章节，均零副作用、100% 成功率。
