## Why

当前 `app/runner.py` 运行完只在终端打印 `final_result()` 和 token 用量，没有可视化测试报告。多人协作、CI/CD、失败回归排查时，无法直观看到「每一步成功/失败 + 每一步页面截图」，尤其是失败时难以快速定位是哪一个用例步骤、页面当时长什么样。本 change 补齐「HTML 测试报告」能力：一次运行结束后自动产出一份可按用例步骤浏览、每步带状态与截图的 HTML 报告。

## What Changes

- 新增 **HTML 测试报告生成能力**：运行结束后，把 `AgentHistoryList`（browser-use 执行历史）+ 用例 YAML 映射成一份可视化 HTML 报告。
- 报告按 **YAML 用例步骤**（goto/input/click/verify…）分节，每节内展开其对应的 **LLM 执行子步骤**，每个子步骤带截图。
- **用例步骤级判定**（红/绿）：以最终状态为准——某用例步骤内部即使 LLM 子步骤失败重试多次，只要最终成功即判成功，仅最终仍未成功判失败。
- 产出为 **HTML + 独立截图目录**：`reports/<用例名>/<时间戳>/report.html` + `screenshots/`，HTML 用相对路径引用截图。
- 截图保留策略：正常成功的子步骤全保留；失败重试时只保留「第一次失败」与「最终成功」两张。
- 报告内容默认「标准」（状态 + 截图 + 动作 + 耗时 + 失败原因）；提供配置项切换到「详细」（额外含 LLM thinking/next_goal、页面 URL/标题、token 等）。token 用量始终打印到日志文件，便于离线定位。
- 生成时机由命令行 `--report` 控制（默认开启，`--no-report` 关闭），方便 CI/CD 显式控制。

## Capabilities

### New Capabilities

- `test-report`: HTML 测试报告生成——将一次运行的历史与用例步骤对齐，产出按步骤分节、每步带状态与截图的 HTML 报告（含截图落盘、成功/失败判定、日志输出）。

### Modified Capabilities

<!-- 本次为纯新增报告能力，不改动现有 capability（element-memory / popup-watchdog / prompt-profiler）的 spec 级需求。 -->

## Impact

- **新增文件**：
  - `app/report/`（报告生成模块：入口 `__init__.py` + `models.py` 中间模型 + `align.py` 对齐 + `judge.py` 判定 + `screenshots.py` 截图落盘 + `render.py` 渲染）。
- **受影响现有代码**：
  - `app/runner.py`：新增 `--report` flag，运行结束后调用报告生成。
  - `app/config.py` / `config.yaml`：新增 `report` 配置段（输出目录、详细/标准模式、token 日志等）。
- **依赖新增**：倾向复用标准库（`html` / `string.Template` / `base64` / `json`），不引入第三方模板引擎（详见 design 决策）。
- **风险**：中。核心难点是「LLM 执行步骤 → YAML 用例步骤」的对齐为启发式，极端场景可能错位，需「未归类步骤」兜底；对齐方案已对比 A/B/C 三种并选定方案 A（离线序列对齐），详见 design.md。
