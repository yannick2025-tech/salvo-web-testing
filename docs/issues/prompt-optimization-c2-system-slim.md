# Prompt 降本 · 方案 C2（system prompt 精简）实验报告

> 日期：2026-09-14
> 模型：qwen3.7-max
> 用例：`cases/manhattan/smoke.yaml`（登录 + 充电订单查询 + 站点列表查询）
> 前置：方案 C1（工具精简）已验证通过，本报告聚焦 C2 system prompt 精简。

## 1. 背景

计量基线（`prompt-token-breakdown.md`）显示：全程累计口径下 **system 占 39.1%（单次 24,087 chars）**，是 prompt 六部分中的最大头。

browser-use 默认 system prompt（`system_prompt.md`，271 行）里有大量本项目用不到的章节：

| 删除章节 | 原因 |
|---|---|
| `<file_system>` | 文件系统——runner 已通过 `tool_exclude` 排除 `write_file`/`read_file`/`replace_file` 等 |
| `<planning>` | 规划——用例是明确步骤清单，无需 LLM 自主规划 todo |
| `<browser_vision>` | 截图——`use_vision=False` 不读截图 |
| `<examples>` | 示例——todo.md / file 操作示例，依赖被排除的工具 |

这些章节让 LLM「被告知可以用某工具」，但对应工具实际未注册，纯属冗余。

## 2. 优化内容

通过 `override_system_message` 整体替换默认模板为精简版（`browser_use_ext/system_prompt_slim.py`），删除上述四段，保留核心规则：

| 保留章节 | 作用 |
|---|---|
| `<output>` | JSON 输出格式（关键，删除会导致解析失败） |
| `<action_rules>` | 每步 action 数量上限 + 串行执行规则 |
| `<browser_rules>` | 浏览器交互规则（索引、弹窗、403、循环检测） |
| `<task_completion_rules>` | done 调用时机 + success 判定 |
| `<efficiency_guidelines>` | action 组合 / 页面变更顺序 |
| `<reasoning_rules>` | thinking 推理模式 |
| `<critical_reminders>` / `<error_recovery>` | 关键提醒 + 错误恢复 |

配置开关：`config.yaml` → `runner.slim_system_prompt: true`（可回滚）。

## 3. 结果

| 指标 | 优化前 | 优化后 | 降幅 |
|---|---|---|---|
| system 单次字符数（profiler 实测） | 24,087 | **13,060** | **-45.8%** |
| 模板行数 | 271 行 | ~150 行 | -44% |

> 静态模板对比：`system_prompt.md` 24,111 chars → 精简模板 13,072 chars（含 `{max_actions}` 占位符），替换为 `5` 后实测 13,060，与静态预期一致。

## 4. 成功率验证

| 用例 | LLM 调用 | 结果 |
|---|---|---|
| 登录（setup） | 3 步 | ✅ 成功，跳转 `/Home` |
| 充电订单查询 | 6 步 | ✅ 成功，604 条记录 |
| 站点列表查询 | 7 步 | ✅ 成功，南京已勾选 / 江苏未勾选 |

- 3 用例 **100% 成功**，无 JSON 解析错误、无 `done` 截断。
- 删除 `<planning>` / `<examples>` 后，`eval` / `memory` / `next_goal` / `action` 字段输出依然完整稳定。

## 5. 固定开销累计收益（C1 + C2）

| 固定开销（单次 LLM 调用） | 优化前 | 优化后 | 降幅 |
|---|---|---|---|
| system（C2） | 24,087 | 13,060 | -45.8% |
| tools（C1） | 21,040 | 13,781 | -34.5% |
| **合计** | **45,127** | **26,841** | **-40.5%** |

配合 DashScope prompt caching（`total_prompt_cached`），固定前缀（system+tools）进一步降低缓存的 base 费用。

## 6. 观察：Exploration nudge

删除 `<planning>` 后，充电订单 / 站点列表用例在第 5 步起出现 browser-use 内置的
`Exploration nudge injected after N steps without a plan`（LLM 未主动规划时的兜底提示）。

- 影响：每步 context 仅追加约 202 chars（见 profiler per-step 表 `context=202`）。
- 结论：**无害**，不影响成功率，相对 DOM 的 10K+ chars 可忽略。若后续想消除，可在精简版补一句极简 planning 引导，当前无必要。

## 7. 结论

C2 达成目标：system 单次 -45.8%，无输出格式错误，成功率 100%。

至此「方案 C 固定开销瘦身」整体完成，`prompt-fixed-overhead-slim` change 的 C1 + C2 全部验证通过。
