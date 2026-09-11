## 1. 用例结构（case_loader + task_builder）

- [x] 1.1 在 `app/case_loader.py` 新增 `Suite` 模型（`name` / `description` / `setup: list[Step]` / `cases: list[Case]`）
- [x] 1.2 新增 `load_suite(path)`：解析 `setup` + `cases`；仅含 `steps` 的旧格式视为单用例套件（向后兼容）
- [x] 1.3 在 `app/task_builder.py` 新增针对 setup 与单个 case 的任务构造（`build_steps_task`，`build_task` 委托之）

## 2. 会话复用（integration + config）

- [x] 2.1 `create_memory_agent` 增加显式 `browser_session` 参数并透传给 `Agent`
- [x] 2.2 首个 agent 使用 `BrowserProfile(keep_alive=True)`（登录后浏览器不关闭）

## 3. 批跑执行（runner）

- [x] 3.1 实现输入展开：位置参数支持多文件/目录；目录展开为其下 `*.yaml`，去重排序（`_expand_inputs`）
- [x] 3.2 实现套件执行：setup 跑一次（登录），随后每个 case 复用 `browser_session` 依次 `agent.run()`，收集各自的 history（`_run_suite`）
- [x] 3.3 实现 setup 失败处理：登录失败停止后续用例，报告标记「登录失败」、用例「未执行」
- [x] 3.4 最后一个 case 跑完显式 `kill` 会话收尾（try/finally 保证）

## 4. 报告聚合（report）

- [x] 4.1 `generate_report` 改为接收多个结果（`list[RunResult]`）并按平台分块、块内多用例
- [x] 4.2 聚合元信息（总用例数/成功/失败/通过率），单结果时退化为单用例报告（向后兼容）

## 5. 测试与验证

- [x] 5.1 `Suite` 解析与向后兼容单元测试（`tests/test_suite_loader.py`）
- [x] 5.2 输入展开单元测试（文件 / 目录 / 多路径 / 去重排序）
- [x] 5.3 报告聚合单元测试（多结果 → 一份报告、多平台分块、元信息正确）
- [ ] 5.4 跑 `cases/manhattan/smoke.yaml`，人工核对：登录一次、报告 2 条用例、状态与截图正确
