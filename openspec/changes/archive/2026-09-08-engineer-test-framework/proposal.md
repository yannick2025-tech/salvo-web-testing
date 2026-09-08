## Why

当前项目是单个 `uat-login.py` 脚本：模型写死 deepseek、测试步骤以一段自然语言 task 硬编码在脚本里、无依赖管理、无统一配置。随着未来需要支持多个测试用例、多个模型（deepseek / 阿里千问 Qwen3-Max）、以及"LLM 扫描前端自动生成元素记忆"的能力，这种单脚本形态无法扩展，且每个新用例都要复制登录/模型判断等复用逻辑。

## What Changes

- **迁移到 uv 管理**：新增 `pyproject.toml` 与 `uv.lock`，统一依赖与运行入口。
- **模型配置化 + 统一加载**：模型 provider、base_url、model 名、KEY 环境变量全部进配置文件；提供单一 `llm_factory` 集中加载，支持 deepseek 与 Qwen3-Max（使用各自 SDK），用例脚本不再出现复用的 if 判断。
- **项目级统一配置**：登录 URL、模型、记忆等全局配置进统一配置文件，测试用例中不再出现登录 URL 等环境信息。
- **测试用例 YAML 化 + 统一 loader**：用例改为结构化步骤（action/target/locator/params）的 YAML，由统一 loader 读取，再由 task_builder 转成现有可跑通的自然语言 task。
- **统一执行器（runner）**：单一 `runner.py` 接收用例文件路径，完成「加载配置 → 建模型 → 加载用例 → 转 task → 装配 agent → 执行」，不动态生成 py 文件。
- **记忆存储拆分**：元素记忆从单 `elements.json` 拆为按页面/模块的多 JSON + 一个索引文件，解决规模与维护问题。
- **定位信息优先从记忆取**：用例 YAML 中 locator 字段可省略；运行时定位优先命中记忆，未命中再回退 LLM 现场定位。

## Capabilities

### New Capabilities

- `uv-project-setup`: uv 依赖管理、项目布局与运行入口。
- `llm-provider-registry`: 模型配置化与统一加载，支持 deepseek 与 qwen 各自 SDK。
- `case-loader`: YAML 结构化用例的加载、校验与 task 转换。
- `runner`: 统一执行器，接收用例路径并驱动完整测试流程。
- `memory-sharding`: 元素记忆按页面/模块拆分多 JSON 并提供索引。

### Modified Capabilities

<!-- 无既有 spec 需要修改 -->

## Impact

- **新增文件**：`pyproject.toml`、`uv.lock`、`config.yaml`、`app/` 包（`config.py`、`llm_factory.py`、`case_loader.py`、`task_builder.py`、`runner.py`）、`cases/*.yaml`。
- **受影响现有代码**：`uat-login.py` 的逻辑将被 `app/runner.py` + `cases/*.yaml` 取代（保留为参考或迁移后删除）。
- **受影响模块**：`browser_use_ext/memory/store.py`（记忆拆分）、`browser_use_ext/integration.py`（适配统一配置与 llm_factory）。
- **依赖新增**：`pyyaml`（YAML 解析）、qwen SDK（阿里千问）、uv 相关依赖声明。
- **风险**：Qwen3-Max 官方 SDK 与 browser-use 期望的 `BaseChatModel` 接口的适配方式需在实现阶段查证。
