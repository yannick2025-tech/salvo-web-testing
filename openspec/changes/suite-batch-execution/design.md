## Context

当前 `app/runner.py` 的执行链是：`load_case`（单个 `Case`，平铺 `steps`）→ `build_task` → `create_memory_agent` → `agent.run()` 得到一份 `history` → `generate_report` 生成单用例报告。一次运行 = 一个 YAML = 一个用例 = 一份报告。

要支持「登录一次 + 多个用例 + 一份聚合报告」，需要同时改动三层：用例结构（`case_loader`）、执行（`runner` 的会话复用与批跑）、报告（`report` 的聚合）。

已验证的 browser-use 0.13.10 能力：`Agent.__init__` 有 `browser_session` 参数（可复用已存在会话）；`BrowserProfile` 有 `keep_alive`（`agent.close()` 里 `keep_alive=True` 时不 `kill` 浏览器，会话保留）。

## Goals / Non-Goals

**Goals:**

- 一个 YAML 用 `setup`（公共前置）+ `cases`（多个用例）描述一套件，登录只执行一次。
- 同一浏览器会话内依次执行各用例，每个用例独立 `agent.run()`、独立 `history`、独立成败判定。
- 批跑输入支持文件 / 目录 / 多路径混用，聚合为一份报告。
- 向后兼容旧单用例 YAML。

**Non-Goals:**

- 不做用例级并行执行（并发浏览器）；保持顺序执行。
- 不引入跨用例的状态共享/依赖传递（每个用例从 setup 后的状态开始，互不依赖）。
- 不改动 element-memory / popup-watchdog / prompt-profiler 的行为。

## Decisions

### 决策 1：多 agent 复用会话，而非单 agent 一次跑完

**用户疑问（记录以备维护）**：「为什么用多个 agent？登录成功后用例依次执行不可以吗，是因为 history 会污染？」

**答复与结论**：核心原因不只是「history 污染」，而是四个层次。先澄清关键概念——**agent 与浏览器会话是两回事**：`browser_session` 是真实的浏览器窗口（共享它 = 不重启、登录态保留、页面连续）；`agent` 是「任务执行器」（一个 `run()` 循环，有独立 task / history / `is_successful()` / 失败计数）。所以「多 agent」不等于「多次登录」，浏览器从头到尾是同一个会话。

选「多 agent、每个用例独立 `run()`」的四点理由：

1. **用例边界切分难**：单 agent 一次 run 的 history 是一长串 LLM 步骤，事后要切成「setup / case1 / case2」三段只能靠启发式切分，比单 case 内部对齐更难、更易错（该项目已证明对齐易跑偏）。多 agent 让边界由 `agent.run()` 本身保证，无需猜。
2. **失败隔离**：`max_failures` / `max_steps` 是每次 run 独立的。单 agent 跑 N 个用例，case1 失败重试会消耗全局配额、甚至让 agent 提前 done，拖累 case2。多 agent 每个 case 重新计数，互不影响。
3. **token 不跨用例累积**：单 agent 的 history 逐步变长，后跑用例每一步都要带前序所有用例的历史进 prompt（该项目对 token 极敏感）。多 agent 每个 case 从空历史开始。
4. **复用现有记忆学习机制**：`done_callback` 在每次 `run()` 结束时对整段 history 学习一次元素记忆。多 agent 让每个用例各自触发一次学习，判定与记忆都按用例隔离，匹配现有代码。

**替代方案（单 agent 一次 run）**：实现上更简单，但用例边界不可靠、失败与 token 相互拖累、记忆学习无法按用例隔离。放弃。

### 决策 2：YAML 结构 = `setup`（可选）+ `cases`（多个）

```yaml
name: manhattan 冒烟测试
setup:                          # 可选公共前置（登录），只执行一次
  - action: goto
    target: 登录页
  - action: input
    target: 请输入您的账号
    params: { value: "${TEST_ACCOUNT}" }
  - action: input
    target: 请输入您的密码
    params: { value: "${TEST_PASSWORD}" }
  - action: click
    target: 登录按钮
    locator: { id: login }
  - action: verify
    target: 登录成功
    params: { expect: "页面跳转到后台/工作台/首页，不再停留在登录页" }
cases:
  - name: 充电订单查询
    steps: [ ... ]
  - name: 站点列表查询
    steps: [ ... ]
```

- `case_loader` 新增 `Suite` 模型：`name` / `description` / `setup: list[Step]` / `cases: list[Case]`。
- 向后兼容：YAML 顶层只有 `steps`（无 `cases`）→ 视为单用例套件（`setup=[]`，`cases=[该用例]`）。加载函数返回统一的 `Suite`。

### 决策 3：会话复用 = `keep_alive=True` + `browser_session` 透传

- 首个 agent 用 `BrowserProfile(keep_alive=True)` 启动（跑 `setup`，无 `setup` 则跑第一个 case），`run()` 后浏览器不关闭。
- 后续每个 case 新建 agent 时传 `browser_session=上一个 agent.browser_session`，复用同一会话（登录态保留）。
- 最后一个 case 跑完，显式 `await browser_session.kill()` 收尾。
- `create_memory_agent` 增加显式 `browser_session` 参数并透传给 `Agent`；`MemoryIntegration` 依赖的 `_browser_session` 引用随 agent 的 `browser_session` 更新。

### 决策 4：批跑输入展开规则

- 位置参数支持多个；每个参数若是**目录** → 展开为其下所有 `*.yaml`（排序）；若是**文件** → 单个。
- 整体去重、按路径排序，依次执行。
- 所有展开出的套件，最终聚合进**一份**报告（按平台分块，块内多用例）。

### 决策 5：`setup` 失败处理

- `setup`（登录）跑完判定 `is_successful()`；失败则**停止后续用例**，报告标记「登录失败」，所有用例显示「未执行」。
- 报告仍生成，元信息体现失败（失败数=用例总数，通过率 0%）。

### 决策 6：`setup`（登录）不占报告用例行

- 登录是前置，不是「用例」，不进报告用例列表。报告只展示 N 个业务用例。
- 登录失败时，通过报告顶部的「登录失败」标记体现，而非一条用例行。

## Risks / Trade-offs

- **[session 复用依赖 browser-use 内部行为] → 缓解**：`keep_alive` + `browser_session` 参数为公开 API，已实测 `close()` 逻辑；全部 try/except 包裹，复用失败则降级为每个 case 新建会话（退化为重复登录，但报告仍正确）。
- **[多 agent 实例的 integration 状态] → 缓解**：每个 case 的 `MemoryIntegration` 独立创建；弹窗 watchdog / 记忆查询随各自的 `browser_session` 引用工作，互不共享菜单路径等运行时状态。
- **[setup 与首个 case 之间无失败边界] → 缓解**：setup 单独 `run()` 并判定，失败即停，不进入 case 循环。
- **[批跑目录含非用例 yaml] → 缓解**：目录只拾取 `*.yaml`；加载失败（非法结构）记日志并跳过，不影响其余套件。

## Migration Plan

- 纯增量：新增 `Suite` 模型 + runner 套件执行路径 + 报告聚合；旧单用例 YAML 无需改动即可继续运行。
- 回滚：把 runner 的批跑/套件分支切回单用例路径即可，报告端聚合入口保持向后兼容（单结果 = 单用例报告）。

## Open Questions

- 暂无阻塞项。后续可考虑：并发执行多用例、用例间失败快速失败策略、批跑结果的独立子报告（按平台分文件）。
