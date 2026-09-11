## Why

当前 runner 一次只跑一个 YAML 用例：一个 `cases/*.yaml` 的 `steps` 就是一次浏览器会话里的一条完整用例。要跑多个用例，只能写多个 YAML、分别执行——但每个 YAML 都要各自登录，既慢又浪费 token；而且跑出的是多份「每份只有一条用例」的报告，无法在一个报告里看到「总用例 N / 成功 x / 失败 y / 通过率」的聚合视图。

实际业务中，多个用例往往共享同一个前置（登录），并希望一次跑完、聚合出一份报告。本 change 引入「套件（suite）」概念：一个 YAML 用 `setup`（公共前置，登录一次）+ `cases`（多个用例）描述，runner 复用同一个浏览器会话依次执行各用例，最终聚合为一份多用例报告；并支持文件/目录/多路径的批量输入。

## What Changes

- **YAML 结构扩展（`case_loader`）**：新增 `setup`（可选公共前置步骤）+ `cases`（多个用例，每个含 `name`/`steps`）。仅含 `steps` 的旧格式向后兼容（视为单用例套件）。
- **执行（`runner`）**：一个套件在**同一个浏览器会话**里执行——`setup` 跑一次（登录），随后每个 `case` 用新 agent 实例复用同一 `browser_session` 依次执行，不重复登录。
- **批跑输入**：`case` 位置参数支持**文件 / 目录 / 多个文件与目录混用**；目录展开为其下所有 `*.yaml`，去重排序后依次执行。
- **报告聚合（`report`）**：`generate_report` 从「单 (history, case)」升级为「多个结果」，聚合出**一份**报告——元信息显示总用例/成功/失败/通过率，按平台分块，每块下列出多个用例（各可折叠展开步骤/截图）。
- **`setup` 失败**：登录失败即停止后续用例，报告标记登录失败、用例显示「未执行」。

## Capabilities

### New Capabilities

- `suite-batch-run`: 套件批跑——用一个 YAML 描述「公共前置（setup）+ 多个用例（cases）」，复用同一浏览器会话执行（登录一次），支持文件/目录/多路径批量输入，并聚合为一份多用例 HTML 报告。

### Modified Capabilities

<!-- 本次为执行层与报告聚合的新能力；不修改 element-memory / popup-watchdog / prompt-profiler 的 spec 级需求。test-report 的渲染模型已支持多平台多用例（见 html-test-report change），本次仅扩展其聚合入口，无 spec 级行为回退。 -->

## Impact

- **新增/修改文件**：
  - `app/case_loader.py`：新增 `Suite` 模型（setup + cases），兼容旧 `Case`。
  - `app/task_builder.py`：新增针对 setup / 单 case 的任务构造。
  - `app/runner.py`：批跑输入展开 + 套件执行（session 复用）+ 报告聚合调用。
  - `app/report/__init__.py`：`generate_report` 接受多个结果并聚合。
- **受影响现有代码**：
  - `browser_use_ext/integration.py`：`create_memory_agent` 需透传 `browser_session` 以复用会话。
  - `app/config.py` / `config.yaml`：`runner` 段可能需要加 `keep_alive` 开关（默认 true）。
- **依赖新增**：无（复用 browser-use 既有 `browser_session` / `keep_alive` 能力）。
- **风险**：中。session 复用依赖 browser-use 0.13.10 的 `keep_alive` + `browser_session` 透传（已验证可用）；用例边界由独立 `agent.run()` 天然保证（详见 design 决策 1）。
