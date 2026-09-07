## Why

当前元素记忆是单文件 `memory/elements.json`。随着规模增长（单个管理平台即有数十个一级菜单、200–300 个二级菜单、上千页面/功能按钮、上万元素），单文件会越来越大，读取慢、维护难、多人协作易冲突。同时项目未来要支持 4 个不同管理平台（不同域名），记忆需要按平台隔离。而现有登录 URL 是项目级单值，无法让同一套代码框架驱动多个平台。

## What Changes

- **记忆按「平台 + URL path 第一段」分片存储**：`memory/<platform>/<shard>.json`，其中 platform 由域名（host）映射、shard 由 URL path 第一段（稳定对应一级菜单，如 `/station` → `station.json`）映射。LLM 全程无感知，由程序侧根据当前页面 URL 自动路由。
- **引入「平台配置 + 用例组」概念**：新增平台注册表（host → 平台别名/登录 URL），一个平台对应一个用例组（`cases/<platform>/...`）。登录 URL 从项目级下移到平台/用例组级。
- **改造记忆存储路由层**：`ShardedMemoryStore` 的路由键从「按 url_pattern 匹配」升级为「host 映射平台目录 + path 第一段映射分片文件」，并保留对旧单文件 `elements.json` 的读取兼容（迁移期并存）。
- **（可选）保留公共记忆**：登录页等不属于任何一级菜单的通用控件记忆，落入每个平台的 `_common.json`。

## Capabilities

### New Capabilities

- `platform-profile`: 多平台配置与用例组组织——平台注册表（host → 别名/login_url）、用例按平台分目录、URL 从项目级下移到平台级。

### Modified Capabilities

- `memory-sharding`: 记忆分片的路由键由「按页面/模块 url_pattern」演进为「按平台 host + URL path 第一段」，并明确 LLM 无感知的自动路由语义。（该能力源自尚未归档的 `engineer-test-framework` change，本次为 spec 级行为变更。）

## Impact

- **新增文件**：`memory/<platform>/` 目录结构（多平台多分片）、平台注册配置（`config.yaml` 扩展或独立 `platforms.yaml`）、用例组目录 `cases/<platform>/`。
- **受影响现有代码**：
  - `browser_use_ext/memory/store.py`（`ShardedMemoryStore` 路由逻辑重写：host+path 路由）
  - `browser_use_ext/integration.py`（`MemoryIntegration` 初始化分片 store、注入平台上下文）
  - `app/config.py` / `config.yaml`（平台注册表、移除单一 login_url 或改为平台映射）
  - `app/case_loader.py` / `app/task_builder.py`（用例组目录、login_url 从平台配置注入）
  - `app/runner.py`（按平台/用例组解析用例与配置）
- **依赖新增**：无（复用现有 pydantic/pyyaml）。
- **风险**：分片路由依赖「URL path 第一段 = 一级菜单」这一前端约定，若个别菜单不遵循则落入 `_common.json` 或默认分片，需在实现阶段用真实页面校验；迁移期需保证旧 `elements.json` 不失效。
