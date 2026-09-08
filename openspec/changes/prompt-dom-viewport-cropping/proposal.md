## Why

第二阶段计量确认 DOM 占未缓存全价 prompt 的 18.5%（单步峰值 22,260 chars），是大列表页面（站点列表 1171 条、订单 204 条）的主要开销。方案 A（`prompt-parameter-tuning`）尝试用 `max_clickable_elements_length=15000` 简单截断 DOM，结果**失败并已回滚**：调用次数 18→40、total_tokens +137%（257,662→610,815）、用例 2 城市级联选择失败——因为「一刀切截断」会把视口外的关键元素（江苏省 hover 目标、南京市复选框）截掉，LLM 定位失败后反复重试。

进一步调查发现 DOM 膨胀的真正根因：browser-use 的 `viewport_threshold` 默认 **1000**，即「视口底部往下 1000px 内的元素也算可见」，导致大列表页面几百条视口外记录被列入 `selector_map`。而 browser-use 的设计意图本是「只列视口内元素」（system prompt 明确写明，序列化时会加 `more content below viewport - scroll to reveal` 提示），`viewport_threshold=1000` 把这个阈值放得过宽、违背了设计初衷。本 change 收紧该阈值，**恢复「只列视口内」的设计意图**，而非粗暴截断。

## What Changes

- 通过项目层 monkey-patch（不改 `.venv`）把 `DomService` 的 `viewport_threshold` 从默认 1000 收紧为可配置值（初始建议 **200**）。
- 新增配置项，使该阈值可调（便于梯度测试 0/200/500）。
- 预期效果：大列表页面仅列视口内 + 少量缓冲元素，DOM 单步从 22k chars 显著下降，且**关键交互元素（筛选栏、查询按钮、级联面板）保留**（它们在视口内）。

## Capabilities

### New Capabilities

- `dom-viewport-cropping`: DOM 视口裁剪——通过收紧 browser-use 的 `viewport_threshold`，使 DOM 序列化仅保留视口内（含少量缓冲）的可交互元素，恢复「只列视口内」的设计意图，降低大列表页面的 DOM prompt。

### Modified Capabilities

<!-- 本次为纯新增能力，不改动现有 capability 的 spec 级需求。 -->

## Impact

- **新增文件**：项目层 monkey-patch 模块（如 `browser_use_ext/dom_patch.py`）。
- **受影响现有代码**：
  - `browser_use_ext/integration.py`（在 `create_memory_agent` 挂载 patch）
  - `app/config.py` / `config.yaml`（新增 viewport 阈值配置）
  - `app/runner.py`（透传阈值）
- **依赖新增**：无。
- **风险**：视口外的关键元素（需滚动才能看到）不再直接列出，LLM 需按「scroll to reveal」提示滚动——可能增加滚动步骤（多几次调用）。需验证成功率保持 100%、总 token 净下降。
- **前置教训**（方案 A，详见 `prompt-parameter-tuning/design.md`）：绝不采用「截断到固定字符数」的方式，必须「智能保留视口内 + 关键元素」。
