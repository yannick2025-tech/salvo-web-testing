## 1. 用例结构（case_loader + task_builder）

- [ ] 1.1 在 `app/case_loader.py` 新增 `Suite` 模型（`name` / `description` / `setup: list[Step]` / `cases: list[Case]`）
- [ ] 1.2 新增 `load_suite(path)`：解析 `setup` + `cases`；仅含 `steps` 的旧格式视为单用例套件（向后兼容）
- [ ] 1.3 在 `app/task_builder.py` 新增针对 setup 与单个 case 的任务构造（复用 `build_task` 的步骤转文本逻辑）

## 2. 会话复用（integration + config）

- [ ] 2.1 `create_memory_agent` 增加显式 `browser_session` 参数并透传给 `Agent`
- [ ] 2.2 首个 agent 使用 `BrowserProfile(keep_alive=True)`（登录后浏览器不关闭）

## 3. 批跑执行（runner）

- [ ] 3.1 实现输入展开：位置参数支持多文件/目录；目录展开为其下 `*.yaml`，去重排序
- [ ] 3.2 实现套件执行：setup 跑一次（登录），随后每个 case 复用 `browser_session` 依次 `agent.run()`，收集各自的 history
- [ ] 3.3 实现 setup 失败处理：登录失败停止后续用例，报告标记「登录失败」、用例「未执行」
- [ ] 3.4 最后一个 case 跑完显式 `kill` 会话收尾

## 4. 报告聚合（report）

- [ ] 4.1 `generate_report` 改为接收多个结果（`list[(platform_alias, case, history)]`）并按平台分块、块内多用例
- [ ] 4.2 聚合元信息（总用例数/成功/失败/通过率），单结果时退化为单用例报告（向后兼容）

## 5. 测试与验证

- [ ] 5.1 `Suite` 解析与向后兼容单元测试（含 setup + cases、单用例旧格式）
- [ ] 5.2 输入展开单元测试（文件 / 目录 / 多路径 / 去重排序）
- [ ] 5.3 报告聚合单元测试（多结果 → 一份报告、多平台分块、元信息正确）
- [ ] 5.4 跑 `cases/manhattan/` 目录（拆分后的 2 个用例），人工核对：登录一次、报告 2 条用例、状态与截图正确
