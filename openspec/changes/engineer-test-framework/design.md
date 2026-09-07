## Context

当前项目为一个单体脚本 `uat-login.py`，内含：写死的 deepseek 模型、写死的登录 URL 与账号、以及一整段自然语言 task（登录 + 两个用例）。`browser_use_ext` 提供元素记忆、auto_apply、弹窗看门狗等能力，已能稳定跑通。未来需要支持多模型、多用例、以及"LLM 扫描前端自动生成记忆"的能力，因此需要工程化重构，同时不破坏已验证跑通的记忆/自动设值机制。

## Goals / Non-Goals

**Goals:**
- 用 uv 统一管理依赖与运行入口。
- 模型配置化，支持 deepseek 与阿里千问 Qwen3-Max（各自 SDK），由单一 `llm_factory` 集中加载，用例无重复 if。
- 登录 URL 等项目级环境信息进统一配置，用例中不出现。
- 测试用例 YAML 化（结构化步骤 action/target/locator/params），统一 loader + 单一 runner，不动态生成 py。
- 记忆按页面/模块拆分多 JSON + 索引；用例定位优先命中记忆，未命中回退 LLM。

**Non-Goals:**
- 本次不实现"LLM 扫描前端自动生成记忆"的扫描器本身（只预留 locator 可省略、记忆优先的结构）。
- 不改动 `browser_use_ext` 已验证的 auto_apply/看门狗核心逻辑（仅做配置与存储适配）。

## Decisions

### 决策 1：模型加载用「注册表」模式 + OpenAI 兼容 client
- `config.yaml` 的 `llm.provider` 指定当前 provider；每个 provider 在 `llm_factory` 注册表里有：`api_key_env`、`base_url`、`model`、以及构造 client 的函数。
- **已查证结论**：browser-use 0.13.10 无 qwen 官方 provider；其 `ChatDeepSeek` 底层即用 OpenAI 的 `AsyncOpenAI`（仅换 base_url）。阿里 DashScope 提供 OpenAI 兼容端点，故 qwen3-max 可复用同一套 `AsyncOpenAI` client，仅配置 base_url / api_key / model 即可，无需自写 `BaseChatModel` 适配器。
- **已排除**：自写 qwen SDK 适配器（qwen 官方无专门 SDK 可用，且 OpenAI 兼容更简单稳定）。

### 决策 2：用例定位信息 —— 方案 A（完整 locator） vs 方案 B（简化 locator，记忆优先）

**方案 A：用例内写完整 locator**

每个步骤在 YAML 里显式写 `locator`（placeholder / class / 菜单路径 / xpath 等），运行时直接按用例给的定位操作。

```yaml
steps:
  - action: input
    target: 账号输入框
    locator: { placeholder: 请输入您的账号 }   # 显式定位
    params: { value: "your-account" }
  - action: click
    target: 登录按钮
    locator: { id: login }                    # 显式定位
  - action: click
    target: 单据时间下拉
    locator: { role: combobox, class: el-select }   # 显式定位
```

- 优点：定位确定性强，不依赖记忆是否已就绪。
- 缺点：定位细节写进用例，编写成本高、易错；且与"扫描前端生成的记忆"重复，两份数据易漂移不一致，前端变更要同时改两处。

**方案 B（选定）：用例只写意图，locator 优先从记忆取**

用例只写 `action` + `target`（意图） + 必要 `params`，`locator` 可省略；定位统一由记忆承载。

```yaml
steps:
  - action: input
    target: 账号输入框
    params: { value: "your-account" }
  - action: click
    target: 登录按钮
  - action: click
    target: 单据时间下拉
```

运行时定位解析顺序：**记忆命中 > 用例显式 locator（兜底） > LLM 现场定位（最终兜底）**。

- 优点：用例聚焦"做什么"，不含易变定位细节，可读性强；定位单一数据源（记忆），避免两处不一致；记忆越跑越准、越跑越省。
- 缺点：首次运行若记忆为空，需 LLM 现场试错定位（已有 auto_apply/记忆学习兜底）。

**为何选 B：**
1. 与既定方向一致——"未来用 LLM 扫描前端，locator 都自动放记忆中"，用例无需重复写定位；
2. 单一数据源原则，避免用例与记忆两处定位不一致的维护成本；
3. 用例大幅简化，从"定位细节"下沉为"业务意图"，更贴近测试人员视角。

### 决策 3：task 转换保持现有可跑通模式
- `task_builder` 把结构化 steps 转成与当前 `uat-login.py` 一致的自然语言 task 文本，再交给 `create_memory_agent`。
- 理由：现有自然语言 task 已稳定跑通，结构化只是"来源归一化"，执行侧行为不变，风险最小。

### 决策 4：记忆按页面/模块拆分 + 索引
- `memory/` 下按模块多 JSON（如 `login.json`、`charge-order.json`、`station-list.json`）+ 一个 `index.json` 记录「文件 → url_pattern」映射。
- `browser_use_ext/memory/store.py` 增加"多文件 + 索引"读取/写入适配，兼容现有 `elements.json` 的单文件接口（迁移期可并存）。

### 决策 5：runner 作为唯一入口，不动态生成 py
- `python -m app.runner cases/<case>.yaml`：加载配置 → 建模型 → 加载用例 → 转 task → `create_memory_agent` → 执行。
- 用 CLI 参数指定用例文件路径，符合用户"单一接收器"诉求，避免动态生成 py 带来的维护/注入风险。

## Risks / Trade-offs

- **Qwen 采用 OpenAI 兼容端点** → qwen3-max 通过 DashScope 的 OpenAI 兼容接口接入（复用 `AsyncOpenAI` client），需在真实环境验证 base_url/model 名正确。
- **记忆拆分可能引入回归** → 迁移期保留对旧单文件 `elements.json` 的读取兼容，逐步切换。
- **结构化 → 自然语言的转换可能丢失语义**（如"江苏不勾选、南京勾选"这种否定语义）→ task_builder 对 action 类型做精确措辞映射，并为关键否定语义保留 `params.negative: true` 之类的显式字段。
- **runner 装配参数需与现有 `create_memory_agent` 签名对齐** → 实现时核对 `create_memory_agent` 入参，避免破坏已跑通行为。

## Open Questions

1. 现有 `uat-login.py` 是否保留为参考样例，还是迁移完成后删除？
2. 记忆 index.json 与各模块 json 的读写锁/并发策略（当前单进程顺序执行，暂可无锁，记为后续关注点）。
