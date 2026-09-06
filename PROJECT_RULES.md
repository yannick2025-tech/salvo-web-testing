# 项目规范（Project Rules）

本文件是 py-web-testing 项目的通用约定。所有后续 AI 助手 / 协作者在编写代码、
提交变更时应遵循本文件。

---

## 1. Git Commit Message 规范

统一采用 **Conventional Commits** 风格，格式如下：

```
<type>(<scope>): <subject>
```

- **type**（必填，小写）：
  - `feat`：新功能
  - `fix`：缺陷修复
  - `docs`：文档变更
  - `refactor`：重构（不改变行为）
  - `test`：测试相关
  - `chore`：构建/工具/杂项（依赖、配置、脚本等）
  - `perf`：性能优化
- **scope**（可选）：变更影响的模块，如 `memory`、`watchdog`、`integration`、`uat-login`。
- **subject**（必填）：
  - 使用祈使句、现在时（如 `add`、`fix`、`update`，不用 `added`/`fixed`）。
  - 首字母小写，结尾不加句号。
  - 不超过 72 字符，简洁描述"做了什么、为什么"。
- **语言**：commit message（type/scope/subject/body）**一律使用英文**。

### 可选 body

当变更较复杂时，在 subject 后空一行补充 body，逐条说明动机与要点：

```
<type>(<scope>): <subject>

- 背景/动机
- 关键改动点
```

### 示例

- `feat(memory): add auto-apply for date-range controls`
- `fix(integration): correct Runtime.evaluate result parsing`
- `docs(lesson-learned): record el-date-range-picker input_enter debugging`
- `chore: add gitignore and project rules`

---

## 2. 工程化约定

- **依赖管理**：使用 `uv`（`uv sync` 安装，`uv run ...` 运行），不手写 requirements.txt。
- **统一配置**：项目级配置在根目录 `config.yaml`（模型 provider、登录 URL、记忆、弹窗看门狗）。
- **模型加载**：统一走 `app/llm_factory.py` 的 `create_llm()`，新增模型只需在注册表加一项，用例/runner 不得出现复用的 if 判断。
- **测试用例**：用 YAML（`cases/*.yaml`）结构化步骤（action/target/locator/params）；locator 可省略，定位优先从记忆取。
- **执行入口**：`python -m app.runner cases/<case>.yaml`，不动态生成 py 文件。
- **登录 URL 等环境信息**只出现在 `config.yaml` 的 `app.login_url`，用例中不出现。

## 3. 约定

- 不要擅自执行 `git commit`：只生成 commit message 等用户确认后再提交。
- 敏感信息（`.env`、密钥、token、密码）一律不进入版本库，已由 `.gitignore` 排除。
- 提交前移除临时脚本 / 调试文件。
