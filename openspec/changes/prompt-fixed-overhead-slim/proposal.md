## Why

经过计量与三轮 DOM 侧优化（视口裁剪 -6.2%、截断失败、折叠失败），DOM 侧已无安全空间。剩余 prompt 大头是**固定开销 `system(39.1%) + tools(34.1%) = 73%`**（全程累计口径）：system 单次 24,087 chars、tools 单次 21,040 chars。虽然 DashScope 的 prompt caching 已兜底约 30%（`total_prompt_cached`），但固定开销仍构成缓存的 base 费用，且 system prompt 里大量内容（file_system、planning、browser_vision、examples）与 tools 里大量工具（search、upload_file、save_as_pdf、文件操作等）本项目根本用不到。本 change 精简这两块固定开销，是继 DOM 之后的第二个降本维度。

## What Changes

- **精简工具（低风险，第一阶段）**：通过 `Tools(exclude_actions=[...])` 排除本项目明确用不到的工具（search、upload_file、save_as_pdf、write_file、replace_file、read_file、find_text、close 等），tools 定义预计从 21,040 chars 降至 ~10k chars。
- **精简 system prompt（高风险，第二阶段）**：通过 `override_system_message` 替换 271 行模板为精简版，删除本项目无关的章节（file_system、planning、browser_vision、examples 等），保留核心规则（output JSON 格式、action 规则、browser 规则、critical_reminders）。

## Capabilities

### New Capabilities

- `tool-slimming`: 工具精简——通过排除本项目用不到的工具，降低 tools 定义的 token 开销。
- `system-prompt-slimming`: 系统提示精简——通过替换精简版 system prompt，降低 system message 的 token 开销。

### Modified Capabilities

<!-- 本次为纯新增能力，不改动现有 capability 的 spec 级需求。 -->

## Impact

- **新增文件**：精简版 system prompt 模板（如 `browser_use_ext/prompts/system_prompt_slim.md`）、工具排除清单配置。
- **受影响现有代码**：
  - `browser_use_ext/integration.py`（`create_memory_agent` 构造 `Tools(exclude_actions=...)` 并透传 `override_system_message`）
  - `app/config.py` / `config.yaml`（工具排除清单、system prompt 精简开关）
- **依赖新增**：无。
- **风险**：
  - **工具排除错误 → 用例失败**：仅排除「明确用不到」的工具，保留所有可能用到的（extract/search_page/find_elements/evaluate/dropdown 等）。
  - **system prompt 删错规则 → LLM 输出格式错误 → 解析失败**：这是高风险项，需逐段删减 + 回归验证；第二阶段需谨慎。
- **前置结论**：DOM 侧已到极限（详见 `prompt-optimization-experiments.md`），本 change 是第二个降本维度。
