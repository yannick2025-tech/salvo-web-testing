## Context

`browser-use 0.13.10` 的 `agent.run()` 返回 `AgentHistoryList`，其中 `.history` 是一串 `AgentHistory`（每个元素是一次 **LLM 执行步骤**）。每个 `AgentHistory` 携带：

- `model_output`（`AgentOutput`）：`thinking` / `evaluation_previous_goal` / `next_goal` / `action`（动作列表，如 `click_element index=12`）。
- `result`：`ActionResult` 列表，含 `is_done` / `success` / `error` / `extracted_content`。
- `state`（`BrowserStateSummary`）：`screenshot`（base64 PNG）、`url`、`title`、`dom_state.selector_map`（index → 元素文本等）。

因此**每一步的截图天然已存在**（即使 `use_vision=False`，截图仍作为浏览器状态被采集），本 feature 的核心是把 `history + 用例` 渲染成 HTML，难点在于「LLM 执行步骤 → YAML 用例步骤」的对齐。

现状约束：项目分层为 `app/`（执行层：config / case_loader / task_builder / runner）与 `browser_use_ext/`（扩展层：integration / memory / watchdogs / prompt_profiler），且既有约定「复用标准库、不引入第三方依赖、不改 `.venv` 内源码、hook 用 try/except 保护」。

## Goals / Non-Goals

**Goals:**

- 一次运行结束后自动（或经 `--report` 控制）产出 HTML 报告，按用例步骤分节，节内展开 LLM 子步骤与截图。
- 用例步骤级成功/失败判定（红/绿），以最终状态为准。
- 截图落盘到独立目录，HTML 相对路径引用。
- 标准/详细两种报告内容模式可配置；token 用量写入日志文件。

**Non-Goals:**

- 不做「LLM 步骤 → 用例步骤」的完美语义对齐（启发式 + 未归类兜底即可）。
- 不引入第三方模板引擎 / 报表库。
- 不修改 `.venv` 内 browser-use 源码。
- 不改动现有记忆 / 弹窗 / 计量等 capability 的行为。

## Decisions

### 决策 1：对齐策略 = 离线序列对齐（方案 A）

**背景**：报告要求「按 YAML 用例步骤分节，节内展开对应 LLM 子步骤」。但 browser-use 内部一个用例步骤会被 LLM 拆成多个执行步骤（如 `select_option` = 点击展开 + 点击选项两个 LLM 步），两者非一一对应，必须做对齐。候选三方案：

- **方案 A：离线序列对齐（事后纯函数）**。`agent.run()` 结束后，独立报告模块对 `history` 做序列对齐，映射回用例步骤再生成报告。
  - 优点：完全解耦，不碰 agent 执行路径；报告生成为纯函数，可单测、可重放（history 落盘后任何时候可重生成）；符合项目 `app/` 与 `browser_use_ext/` 分层风格。
  - 缺点：对齐为启发式，`click`/`check`/`select_option` 都映射为 `click_element`，极端场景可能错位，需「未归类步骤」兜底。
- **方案 B：执行期实时归档（在线挂钩）**。复用 `register_new_step_callback`，每执行一步即归档到「当前用例步骤」，结束时直接生成。
  - 优点：能拿到实时上下文（如 follow_memory 命中的记忆 key），对齐信号更丰富。
  - 缺点：耦合进执行路径、风险高；对齐逻辑散在回调里难单测；报告不可重放。
- **方案 C：锚点标记（让 LLM 上报步骤号）**。给 task 文本每个步骤编号（已有），并 hack `AgentOutput` 让 LLM 每步上报「当前步骤号」。
  - 优点：对齐最精确（若 LLM 配合）。
  - 缺点：依赖 LLM 遵守、实际不可靠；需改 browser-use 输出模型、侵入性最强，收益不稳定。

**选方案 A 的理由**：把报告做成「输入 history + 用例 → 输出 HTML + 截图」的纯函数，最容易单元测试、最稳定、可重放，也最贴合项目「执行层 / 扩展层分离 + 纯项目层 patch」的既有风格；对齐不准处由「未归类步骤」兜底，不影响报告可用性。方案 B 的实时上下文收益可用「从 `history` 反查 selector_map / result」近似补足，方案 C 的精确性不可依赖。

### 决策 2：对齐算法 = 动作类型 + 目标文本的贪心匹配，未匹配兜底

- **动作类型映射**：把 LLM 步骤动作映射为用例动作类别——`go_to_url`→`goto`、`input_text`→`input`、`click_element`→`click`/`select_option`/`check`（歧义，需文本辅助）、`hover_element`→`hover`、`done`→`conclude`；`verify` 无固定动作，靠 `next_goal`/`evaluation_previous_goal` 辅助判定。
- **目标文本反查**：LLM 动作只带 `index`，需从 `state.dom_state.selector_map[index]` 反查元素文本，与用例步骤的 `target` 做文本匹配（子串/包含）。
- **贪心推进**：维护「当前用例步骤」指针，按 LLM 步骤顺序，若其动作类型 + 元素文本与当前（或下一个）用例步骤匹配则归入并推进指针；不匹配的 LLM 步骤归入当前步骤但标记「未精确对齐」，连续无法归类的整体落入「未归类」区。
- **降级兜底**：无法映射到任何用例步骤的 LLM 步骤，统一展示在报告末尾的「未归类步骤」区，保证不丢信息。

### 决策 3：判定规则 = 以最终状态为准（final-state-wins）

用例步骤三态：**成功（绿）/ 失败（红）/ 未执行（灰）**。

- 一个用例步骤内部所有 LLM 子步骤中，若**最后一个子步骤最终成功**（无 `error` 且 `success` 非 False），则该用例步骤判成功——即使中间子步骤失败重试多次（用户明确要求：S2 失败 4 次第 5 次成功仍算成功）。
- 若最后一个子步骤失败，或 agent 在该步骤处触发 `max_failures` 提前终止，则该步骤判失败。
- agent 提前终止导致从未触及的后续用例步骤，判「未执行」。

### 决策 4：产出结构 = `reports/<用例名>/<时间戳>/`

- 输出目录：`reports/<slug(用例名)>/<YYYYMMDD-HHMMSS>/`，内含 `report.html` 与 `screenshots/`。
- 截图命名：`screenshots/<step>-<substep>.png`（用例步骤序号-子步骤序号），HTML 用相对路径 `screenshots/...` 引用。
- `slug`：用例名去除非法文件名字符、空格转 `-`，长度截断。

### 决策 5：截图落盘策略 = 失败重试只留「首次失败 + 最终成功」

- 正常成功的子步骤：每个都落盘截图。
- 同一用例步骤内出现连续失败重试：仅保留「第一次失败的截图」与「最终成功的截图」，中间重复失败截图丢弃（用户明确要求，控制体积同时保留「卡点」与「最终通过」两个关键画面）。

### 决策 6：HTML 渲染 = 标准库，不引入 Jinja2

报告结构固定（用例步骤分节 + 子步骤卡片 + 截图 + 状态），用标准库 `html.escape` + 字符串拼接 + 内联 CSS 的静态模板即可满足；符合项目「零新依赖」约定。

- 替代（引入 Jinja2）：模板更易维护，但引入第三方依赖、违背现有约定。放弃。

### 决策 7：报告内容模式 = 标准/详细配置项 + token 日志文件

- 默认「标准」：状态 + 截图 + 动作类型/目标 + 耗时 + 失败原因（如有）。
- 配置项 `report.detail`（默认 `false`）：`true` 时报告额外展示 LLM `thinking`/`next_goal`、页面 URL/标题、每步 token 等元数据。
- token 用量**始终**打印到日志文件（`reports/<用例名>/<时间戳>/token_usage.log`），不塞进标准报告正文；同时保留现有 stdout 打印。

### 决策 8：异常/中断时尽力生成报告

无论 `agent.run()` 正常返回、抛异常、还是中途失败，`runner` 都用 `try/except` 包裹报告生成：只要能拿到 `history`（哪怕是部分）就尽量生成报告，让失败场景也有可看的截图与步骤状态；报告生成本身的任何异常都不影响主流程。

## Risks / Trade-offs

- **[对齐错位（click/check/select_option 歧义）] → 缓解**：动作类型 + 元素文本双重匹配；未精确对齐的步骤标记「未精确对齐」，整体无法归类的落入「未归类」区，不静默丢信息。
- **[`verify` 步骤无固定动作、难以定位边界] → 缓解**：用 `next_goal` / `evaluation_previous_goal` 文本与用例步骤 `target`/`expect` 做关键词匹配来判定边界；失败时降级为「归入最近一个未闭合用例步骤」。
- **[截图体积随步骤数膨胀] → 缓解**：决策 5 的「失败重试只留首次失败 + 最终成功」策略 + 独立目录（而非 base64 内嵌）控制体积；必要时可后续加截图压缩。
- **[browser-use 数据结构升级导致字段变化] → 缓解**：报告模块所有取值用 `getattr` + try/except 保护，字段缺失时降级（无截图则显示占位、无文本则省略），不影响报告生成。
- **[`use_vision` 或未来版本截图字段为 None] → 缓解**：对 `state.screenshot` 判空，无截图时渲染占位符「无截图」，不报错。

## Migration Plan

- 纯新增能力：新增 `report` 配置段（默认关闭 detail）+ 新增报告模块 + `runner` 挂一个 `--report` flag 与一次生成调用。
- 回滚：`--no-report` 关闭，或撤销 `runner` 中的生成调用即可，执行行为完全不变；不涉及数据迁移。

## Open Questions

- 暂无阻塞项。后续可考虑：报告是否需要内嵌「失败步骤的历史错误信息全文」、是否支持历史报告对比（diff）。
