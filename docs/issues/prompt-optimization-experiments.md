# Prompt 降本实验回顾（总览）

> 日期：2026-09-08
> 目标：降低单次运行 prompt token（实测占 total 的 93.5%~95.4%）
> 环境：qwen3.7-max + `cases/manhattan/login_and_query.yaml`（18 步）
> 前置报告：`qwen3.7-max-memory-vs-no-memory.md`（阶段1 A/B）、`prompt-token-breakdown.md`（六部分计量）

## 一页总览

| 阶段 | 手段 | 结果 | 关键数据 | 状态 |
|------|------|------|---------|------|
| 阶段1 计量 | `PromptUsageProfiler` 六部分计量 | 摸清构成 | system+tools 73%、DOM 18.5%、history 6.6% | ✅ 已落地 |
| 方案A 简单截断 | `max_clickable_elements_length=15000` + `max_history_items=10` | 失败 | invocations 18→40、total +137% | ❌ 已回滚 |
| 方案B 视口裁剪 | `viewport_threshold` 1000→200 | **成功** | total **-6.2%**（257,662→241,697） | ✅ 已落地 |
| 表格折叠 | 结构签名折叠重复行 | 失败 | 误伤导航菜单、破坏翻页 | ❌ 已回滚 |

## 关键结论

1. **token 大头在 prompt 而非 completion**：prompt 占 total 93.5%~95.4%，completion 仅 ~5%。
2. **总量 vs 费用是两个靶心**：总量上 `system(39.1%) + tools(34.1%) = 73%` 是最大头（但被 prompt caching 兜底，`total_prompt_cached` 约 30%）；费用上 `DOM(18.5%) + history(6.6%)` 是未缓存全价大头。
3. **DOM 侧能安全榨取的收益 = -6.2%**（视口裁剪 200）。再往下全是「结构相同 vs 语义相同」的误判坑。
4. **剩余大头是 system+tools 固定开销**，属方案 C（精简 system prompt + 工具定义）的范畴，复杂度与风险不同。

## 详细档案索引

| 实验 | 记录位置 | 核心内容 |
|------|---------|---------|
| 计量基线 | `prompt-token-breakdown.md` + `openspec/changes/prompt-token-optimization/` | 六部分占比、修正「DOM 是绝对大头」的定性判断 |
| 方案A 失败 | `openspec/changes/prompt-parameter-tuning/design.md`「实验结果」章节 | 数据对比表 + 三条根因 + 回滚处置 |
| 方案B 成功 | `openspec/changes/prompt-dom-viewport-cropping/tasks.md`「实验结果」章节 | 梯度测试 0/200/1000，200 为最优点 |
| 表格折叠失败 | `openspec/changes/prompt-table-collapse/tasks.md`「实验结果」章节 | 误伤菜单 + 破坏翻页的根因 |

## 教训（供后续回顾）

1. **简单截断（固定字符数/条数）→ 丢关键元素/上下文 → 重试暴涨**：方案 A 截 DOM 到 15000 把城市级联关键元素切掉、截历史到 10 丢上下文，LLM 反复试错，token 反涨 2.4 倍。
2. **自动识别「结构相同」无法区分「同质冗余」和「语义不同」**：表格折叠的签名 `(tag, class, 子 tag)` 把导航菜单项也当成「重复行」折叠，导致 LLM 找不到菜单；且会破坏翻页用例。
3. **视口裁剪是唯一安全有效的 DOM 优化**：它「恢复 browser-use 的设计意图」（只列视口内元素），而非「新造裁剪规则」，方向天然正确、不误伤。
4. **降本要区分两个维度**：降「token 总量」看 system+tools（有缓存兜底）；降「费用」看 DOM/history（未缓存全价）。二者优化手段不同。
5. **每个实验都留档案**：成功保留成果，失败记录「数据 + 根因 + 回滚」，避免后人重蹈。

## 当前基线

- 已生效优化：`viewport_threshold=200`（config.yaml）
- 效果：total_tokens 257,662 → 241,697（-6.2%），成功率 2/2，invocations 18 不增
- 待探索：方案 C（精简 system prompt + 工具定义）
