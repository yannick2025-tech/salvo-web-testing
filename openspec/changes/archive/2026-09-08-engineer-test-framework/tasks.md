## 1. uv 项目初始化

- [x] 1.1 创建 `pyproject.toml`，声明项目元数据与依赖（browser-use、pydantic、pyyaml、qwen SDK 等）
- [x] 1.2 生成 `uv.lock` 并确认 `uv sync` 可安装依赖
- [x] 1.3 确定运行入口（`python -m app.runner`）并写入项目说明

## 2. 统一配置与模型加载

- [x] 2.1 新建 `config.yaml`，包含 llm（deepseek/qwen 两套）、登录 URL、记忆配置等全局项
- [x] 2.2 实现 `app/config.py` 用 pydantic 加载与校验配置
- [x] 2.3 查证 browser-use 0.13.10 对 qwen provider 的支持方式（内置 or 需适配器）
- [x] 2.4 实现 `app/llm_factory.py` 注册表模式，支持 deepseek 与 Qwen3-Max 各自 SDK 的统一加载
- [x] 2.5 移除 `uat-login.py` 中写死的模型与登录 URL 逻辑

## 3. 用例 loader 与 task 转换

- [x] 3.1 定义 YAML 用例 schema（name、steps：action/target/locator/params），编写示例 `cases/login_and_query.yaml`
- [x] 3.2 实现 `app/case_loader.py` 加载并校验 YAML 用例
- [x] 3.3 实现 `app/task_builder.py` 将结构化步骤转成现有自然语言 task 文本（含否定语义措辞）

## 4. 统一 runner

- [x] 4.1 实现 `app/runner.py`，接收用例路径并串联「配置→模型→用例→task→agent→执行」
- [x] 4.2 对齐 `create_memory_agent` 入参，确保记忆/auto_apply 行为不变
- [x] 4.3 用现有登录+两用例验证 runner 端到端跑通

## 5. 记忆拆分

- [x] 5.1 设计记忆多文件目录结构与 `index.json` 索引 schema
- [x] 5.2 改造 `browser_use_ext/memory/store.py` 支持多文件 + 索引读取，保留旧单文件兼容
- [x] 5.3 将现有记忆迁移为按页面拆分的多 JSON，并回归单测

## 6. 验证与收尾

- [x] 6.1 回归 `tests/test_element_memory.py` 全绿
- [x] 6.2 更新 `PROJECT_RULES.md` / README 说明 uv 与 runner 用法
- [x] 6.3 确认 `.gitignore` 覆盖新增产物（uv.lock 应入库，.venv 忽略）
