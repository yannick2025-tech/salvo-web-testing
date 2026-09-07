## Context

项目已通过 `engineer-test-framework` change 完成工程化：uv + `config.yaml` + `llm_factory` + YAML 用例 + 统一 `runner`，并引入了 `ShardedMemoryStore`（多 JSON + index）作为记忆分片的雏形。当前 `ShardedMemoryStore._route_file` 用 `url_pattern`（glob）做分片路由，但并未真正落地「按菜单/模块」的稳定路由语义；实际生产仍主要走单文件 `elements.json`。

本次要解决的规模与多平台问题：

- **规模**：单个管理平台有几十个一级菜单、200–300 个二级菜单、上千页面/功能按钮、上万元素。单文件记忆读写慢、维护难。
- **多平台**：未来 4 个管理平台，且**不同平台 = 不同域名（host）**。
- **URL 归属**：当前 `app.login_url` 是项目级单值，无法驱动多平台。

两条已确认的前端行为约束（决定方案）：

1. **一级菜单点击不改变 URL**，仅展开子菜单；**二级菜单点击后 URL 才变**，且 URL path 第一段稳定对应一级菜单（如 `电站管理 → 站点列表` 对应 `/station/site/list`；`订单管理 → 充电订单管理` 对应 `/order/charge-order/list`）。
2. **不同管理平台是不同域名**。

## Goals / Non-Goals

**Goals:**

- 记忆按「平台 + 一级菜单」分片，单文件规模可控、可维护。
- 分片路由由程序侧根据当前 URL 自动完成，**LLM 无感知**（不需要 LLM 知道有 4 个平台、几十个文件）。
- 支持多平台：host 天然区分平台，记忆按平台目录隔离。
- 登录 URL 从项目级下移到平台/用例组级，一套代码框架驱动所有平台。

**Non-Goals:**

- 不改 LLM 侧接口（`follow_memory(hint=...)` 语义不变）。
- 不改 `auto_apply`、弹窗看门狗等已验证的核心执行逻辑（仅做存储路由与配置适配）。
- 本次不做「前端自动扫描生成记忆」的扫描器（延续上一 change 的 non-goal）。
- 不引入分布式/并发写锁（当前仍单进程顺序执行）。

## Decisions

### 决策 1：分片路由键 —— 方案 A（URL 驱动） vs 方案 B（菜单名） vs 方案 C（单文件+内存索引）

**方案 A（选定）：URL 驱动的分片 + 平台子目录 + 程序自动路由**

- 目录结构：
  ```
  memory/
    manhattan/            # 平台别名，由 host 映射
      _common.json        # 公共记忆（登录页、跨菜单通用控件）
      order.json          # /order/*  → 订单管理
      station.json        # /station/* → 电站管理
    charging/             # 第二个平台
      _common.json
      ...
  ```
- 路由键：`host → 平台目录`，`path 第一段 → 分片文件`（如 `/station` → `station.json`）。
- 读：`step_callback` 拿到 `state.url`，解析 host + path 第一段，定位 shard，在 shard 内用现有 `MemoryMatcher` 匹配。
- 写：learner 学到的记忆，用 `context.url_pattern` 解析出 host + path 第一段，路由到对应 shard（现有 `_route_file` 由 glob 改为 host+path 解析）。
- LLM 职责不变：仍只传 `follow_memory(hint=控件文案)`。

**方案 B：按一级菜单名分片**

- 路由键 = 菜单名（如 `memory/订单管理.json`）。
- 缺点：菜单名靠 LLM 推断（`_infer_menu_path_from_output`），这正是此前噪声记忆的根源；跨菜单用例时 LLM 得"知道"自己在哪个菜单，不可靠；菜单名会重复（多平台都可能有"订单管理"）、会改文案。

**方案 C：保持单文件 + 启动时内存建索引**

- 磁盘仍单文件，加载进内存建 hash 索引。
- 缺点：解决不了"维护不方便"；上万条单文件每次写回都整体序列化，越跑越慢。

**为何选 A：**

1. **LLM 无感知**：URL 是程序天然拿得到的稳定信号，不依赖 LLM 推断，彻底避免菜单名噪声问题。
2. **一个信号统一两个问题**：host 区分平台、path 第一段区分一级菜单，把"分片索引"和"多平台"用同一稳定信号解决。
3. **跨菜单用例天然支持**：每步 URL 不同，程序自动切换 shard，无需 LLM 参与路由。
4. **改动最小、风险最低**：集中在 store 路由层 + 配置层，LLM 侧接口零改动。

### 决策 2：平台与用例组组织

- **平台注册表**：`config.yaml` 新增 `platforms` 段，形如：
  ```yaml
  platforms:
    manhattan:
      host: ${MANHATTAN_HOST}      # 从 .env 注入，避免泄露内网域名
      login_url: ${MANHATTAN_LOGIN_URL}
    charging:
      host: ${CHARGING_HOST}
      login_url: ${CHARGING_LOGIN_URL}
  ```
- **用例组**：`cases/<platform>/<case>.yaml`，一个平台 = 一个用例组。`runner` 通过 `--platform` 或从用例路径推断平台，从而注入对应的 `login_url` 与记忆目录。
- **登录 URL 归属**：从 `app.login_url`（项目级）移除，改由平台配置提供；用例 YAML 中仍不出现 URL。

### 决策 3：迁移与兼容

- `ShardedMemoryStore` 升级路由逻辑，同时保留：若 `memory/` 下不存在平台目录/分片索引，则回退读取旧单文件 `elements.json`（迁移期并存）。
- 旧 `elements.json` 里已有的记忆，在首次命中或学习时按 `url_pattern` 重新路由到对应平台分片（惰性迁移），或提供一次性迁移脚本。

### 决策 4：路由解析的健壮性

- host 通过「平台注册表」做精确映射（`host == platform.host`），不支持通配，避免误路由。
- path 第一段解析：取 `urlparse(url).path` 的第一段；若 URL 无法解析（如登录页 `/Login` 或空 path），落入 `_common.json`。
- 若某二级菜单的 URL 第一段与一级菜单不对应（前端约定例外），记忆会落默认分片，不影响正确性，仅降低分片精度——作为已知 trade-off 记录。

## Risks / Trade-offs

- **[前端约定：path 第一段 = 一级菜单] → 分片精度下降**：若个别菜单不遵循该约定，其记忆会落 `_common.json` 或默认分片，读取仍正确、只是分片不够精准。缓解：实现阶段用真实页面枚举校验，必要时在平台注册表增加「host + path 前缀 → 别名」的显式映射覆盖。
- **[多平台同构菜单重复] → 记忆不共享**：不同平台若存在语义相同的控件，记忆按平台隔离不会自动复用。缓解：本期接受隔离（符合"平台间不串味"预期）；未来可加跨平台公共分片。
- **[迁移期兼容] → 双写/回退复杂度**：旧单文件与分片并存可能造成心智负担。缓解：惰性迁移 + 明确回退规则，测试覆盖单文件回退路径。
- **[host 精确匹配] → 环境切换（uat/生产）需改注册表**：不同环境的 host 不同，需在注册表各配一份。缓解：平台注册表天然支持多环境条目，按 host 精确匹配即可。

## Migration Plan

1. 在 `config.yaml` 增加 `platforms` 注册表（当前仅 `manhattan` 一个平台），并移除项目级 `app.login_url`。
2. 改造 `ShardedMemoryStore`：`_route_file` 由 glob url_pattern 改为「host 映射 + path 第一段」；新增 `resolve_platform(host)` 与 `resolve_shard(path)`。
3. 改造 `MemoryIntegration` / `runner` / `task_builder`：注入平台上下文与 login_url。
4. 将现有 `memory/elements.json` 里的记忆惰性迁移到 `memory/manhattan/` 分片（或保留回退读取）。
5. 回归 `tests/test_element_memory.py`，新增多平台路由与回退用例。
6. 回滚策略：保留旧单文件读取分支，任何路由异常均可回退到单文件路径。

## Open Questions

1. 平台别名（目录名）用人工指定的 `manhattan` 这类语义名，还是直接用 host？——倾向语义别名，目录可读性更好。
2. `_common.json` 是否需要按平台各一份，还是全局共享一份？——倾向平台各一份（避免平台间串味）。
3. 是否需要一次性迁移脚本（显式迁移），还是纯惰性迁移即可？——倾向惰性迁移 + 可选脚本。
