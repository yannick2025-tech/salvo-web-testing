## ADDED Requirements

### Requirement: uv 项目与依赖管理
系统 SHALL 使用 uv 管理依赖与运行入口，提供 `pyproject.toml` 与 `uv.lock`。

#### Scenario: 安装依赖
- **WHEN** 用户在项目根目录执行 `uv sync`
- **THEN** 所有运行时依赖（browser-use、pydantic、pyyaml、qwen SDK 等）被安装到项目虚拟环境

#### Scenario: 运行统一入口
- **WHEN** 用户执行 `uv run python -m app.runner <case.yaml>`
- **THEN** 系统在 uv 环境中启动统一执行器并运行指定用例
