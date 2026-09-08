## Context

计量基线（`prompt-token-breakdown.md`）显示：全程累计口径下 `system(39.1%) + tools(34.1%) = 73%` 是 prompt 最大头（单次 system=24,087 chars、tools=21,040 chars）。DOM 侧三轮优化后已到极限（视口裁剪 -6.2%）。browser-use 提供两个精简入口：`Tools(exclude_actions=[...])`（排除工具）与 `Agent(override_system_message=...)`（替换系统提示）。

## Goals / Non-Goals

**Goals:**

- 排除本项目用不到的工具，降低 tools 定义 token。
- 替换精简版 system prompt，降低 system message token。
- 保持成功率 100%，用 profiler 量化 system/tools 下降。

**Non-Goals:**

- 不改 `.venv` 内 browser-use 源码。
- 不触碰 DOM/history 优化（已到极限）。

## Decisions

### 决策 1：分两阶段，先工具后提示

工具精简是「排除了就不可用」，风险低、可枚举；system prompt 是「删错了就输出格式错误」，风险高、需逐段验证。故先 C1（工具）后 C2（提示），各阶段独立回归。

### 决策 2：工具排除清单（C1）

仅排除「明确用不到」的工具，保留所有可能用到的：

- **排除**：`search`（搜索引擎）、`upload_file`、`save_as_pdf`、`write_file`/`replace_file`/`read_file`（文件操作）、`find_text`、`close`、（`screenshot` 已被 use_vision=False 自动排除）。
- **保留**：`navigate`、`click`、`input`、`wait`、`scroll`、`done`、`go_back`、`switch`、`extract`、`search_page`、`find_elements`、`send_keys`、`dropdown_options`、`select_dropdown`、`evaluate`、`follow_memory`（自定义）。

### 决策 3：system prompt 精简策略（C2，概要）

用 `override_system_message` 替换为精简版，删除本项目无关章节：

- **删除**：`file_system`（不用文件系统）、`planning`（用例是明确步骤）、`browser_vision`（use_vision=False）、`examples` 大部分示例。
- **保留**：`output`（JSON 格式，关键）、`action_rules`、`browser_rules`、`critical_reminders`、`reasoning_rules`、`error_recovery`。

预计 system 从 271 行 → ~180 行、24,087 chars → ~16k chars（-33%）。

### 决策 4：配置化 + 可回滚

工具排除清单与 system prompt 精简均走配置（`config.yaml`），便于回滚。

## Risks / Trade-offs

- **[工具排除错误 → 用例失败] → 缓解**：仅排除明确用不到的；回归同一用例验证成功率 100%；若失败，把误排工具加回白名单。
- **[system prompt 删错规则 → 输出格式错误 → 解析失败] → 缓解**：保留 output JSON 格式与 action 规则；逐段删减、每删一段回归一次；失败即回退该段。
- **[精简后 LLM 行为漂移（成功但操作变啰嗦）] → 缓解**：以 profiler 总 token + 成功率为最终判据，不只盯 system/tools 单列。

## Migration Plan

- 纯配置 + 透传，无数据迁移。
- 回滚：清空工具排除清单 / 关闭 system prompt 精简开关即可。

## Open Questions

- C2 的精简版 system prompt 具体删哪些段落，需在 C1 验证后逐段实测。
- 工具排除后是否影响「翻页/下拉」等未来用例，需用更全的用例回归。
