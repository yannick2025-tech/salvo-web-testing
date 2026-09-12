## 1. 配置与入口

- [x] 1.1 在 `config.yaml` 新增 `report` 配置段（`detail: false`、输出根目录 `./reports` 等）
- [x] 1.2 在 `app/config.py` 新增 `ReportConfig` 模型并挂到 `Config`，含默认值
- [x] 1.3 在 `app/runner.py` 新增 `--report` / `--no-report` 参数（默认生成）

## 2. 报告中间数据模型

- [x] 2.1 新建 `app/report/models.py`，定义 `StepStatus`（成功/失败/未执行）、`ReportSubStep`、`ReportStep`、`ReportCase` 中间模型

## 3. 对齐模块（方案 A：离线序列对齐）

- [x] 3.1 新建 `app/report/align.py`，实现 LLM 动作类型 → 用例动作类别的映射（goto/input/click/select_option/hover/check/verify/conclude）
- [x] 3.2 实现元素文本反查：从 `state.interacted_element` 按动作反查元素文本，用于与用例 `target` 匹配
- [x] 3.3 实现贪心序列对齐：按执行步骤顺序推进「当前用例步骤」指针；无法映射的步骤归入「未归类」区，不静默丢弃

## 4. 判定模块（final-state-wins）

- [x] 4.1 新建 `app/report/judge.py`，实现用例步骤三态判定：以最终状态为准（内部失败重试最终成功 → 成功）；提前终止时后续步骤判「未执行」

## 5. 截图落盘

- [x] 5.1 新建 `app/report/screenshots.py`，实现截图（base64）解码落盘到 `screenshots/<step>-<substep>.png`
- [x] 5.2 实现失败重试保留策略：同一用例步骤内连续失败重试只落盘「第一次失败」与「最终状态」截图

## 6. HTML 渲染与 token 日志

- [x] 6.1 新建 `app/report/render.py`，实现标准模式 HTML 模板（状态 + 截图 + 动作 + 耗时 + 失败原因），用标准库 `html.escape` + 内联 CSS
- [x] 6.2 实现详细模式（`detail: true` 时额外展示 thinking/next_goal、URL/标题、token 元数据）
- [x] 6.3 实现 token 用量写入 `token_usage.log`（报告目录下），并保留现有 stdout 打印

## 7. 入口集成与兜底

- [x] 7.1 新建 `app/report/__init__.py`，实现 `generate_report(history, case, report_config)` 编排入口：对齐 → 判定 → 截图 → 渲染 → 写文件，返回报告目录路径
- [x] 7.2 在 `app/runner.py` 运行结束后按 `--report` 开关调用 `generate_report`，整体用 try/except 包裹（异常/中断也尽力生成，报告失败不影响主流程）

## 8. 测试与验证

- [x] 8.1 为对齐模块编写单元测试（`tests/test_report_align.py`）：动作类型映射、元素反查、贪心对齐、未归类兜底
- [x] 8.2 为判定模块编写单元测试（`tests/test_report_judge.py`）：final-state-wins、提前终止未执行
- [x] 8.3 为截图落盘策略编写单元测试（`tests/test_report_screenshots.py`）：首末截图保留规则
- [x] 8.4 为 `generate_report` 编写集成测试：给定伪造 history + 用例，产出 report.html + screenshots/，且相对路径可解析
- [x] 8.5 跑一次现有用例（后续拆分为 `cases/manhattan/smoke.yaml`），人工核对报告按用例步骤分节、状态正确、截图可显示
