## 1. 平台注册表与配置

- [x] 1.1 在 `config.yaml` 新增 `platforms` 段（别名/host/login_url），当前仅 `manhattan` 一个平台
- [x] 1.2 移除项目级 `app.login_url`，`app/config.py` 增加 `Platform` / `PlatformsConfig` 模型与校验
- [x] 1.3 实现 `resolve_platform(host)` 精确匹配（含未知 host 回退策略）

## 2. 用例组组织与 URL 注入

- [x] 2.1 定义用例组目录约定 `cases/<platform>/<case>.yaml`
- [x] 2.2 `app/runner.py` 支持通过 `--platform` 或从用例路径推断平台
- [x] 2.3 `app/task_builder.py` 的 goto 步骤改用平台登录 URL 注入

## 3. 记忆分片路由改造

- [x] 3.1 `ShardedMemoryStore` 增加 `resolve_shard(path)`：URL path 第一段 → 分片文件名
- [x] 3.2 `_route_file` 由 glob url_pattern 改为「host 映射平台目录 + path 第一段映射分片文件」
- [x] 3.3 增加 `_common.json` 公共分片路由（登录页/无法解析 path 时）
- [x] 3.4 保留旧单文件 `elements.json` 读取回退（迁移期兼容）

## 4. 集成与执行侧适配

- [x] 4.1 `MemoryIntegration` 初始化时注入平台上下文（当前 host → 平台别名/目录）
- [x] 4.2 learner 写入时携带可解析的 host + path，路由到对应平台分片
- [x] 4.3 `auto_apply` 的日期控件记忆查询适配分片路由

## 5. 迁移与验证

- [x] 5.1 将现有 `memory/elements.json` 记忆惰性迁移至 `memory/manhattan/` 分片（或保留回退）
- [x] 5.2 新增多平台路由、跨菜单切换、单文件回退的单元测试
- [x] 5.3 回归 `tests/test_element_memory.py` 全绿
- [x] 5.4 更新 `PROJECT_RULES.md` 说明平台注册与用例组约定
