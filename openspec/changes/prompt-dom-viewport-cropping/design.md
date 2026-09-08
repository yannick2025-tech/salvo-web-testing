## Context

方案 A（`prompt-parameter-tuning`）用 `max_clickable_elements_length=15000` 简单截断 DOM，结果失败并回滚（详见该 change 的 design.md「实验结果」章节）：截断把视口外的关键元素（江苏省 hover 目标、南京市复选框）截掉，LLM 定位失败后反复重试，总 token 反涨 2.4 倍。

技术调查确认根因：browser-use 判定元素「可见」时用 `viewport_threshold=1000`（视口底部往下 1000px 内的元素也算可见），大列表页面大量视口外记录被列入 `selector_map`。而 browser-use 的设计意图本就是「只列视口内元素」（system prompt 明确写明，序列化时会加 `more content below viewport - scroll to reveal` 提示）。`viewport_threshold` 在 `DomService` 实例化时（`dom_watchdog.py:558`）未被传入、`BrowserProfile` 也无此字段，始终用默认 1000。

## Goals / Non-Goals

**Goals:**

- 收紧 `viewport_threshold`，让「只列视口内元素」真正生效，降低大列表页面 DOM prompt。
- 保留视口内的关键交互元素（筛选栏、查询按钮、级联面板），保持成功率 100%。
- 用 profiler 量化 DOM 占比下降与总 token 净变化。

**Non-Goals:**

- 不做「截断到固定字符数」（方案 A 已验证有害）。
- 不做大列表/表格的语义折叠识别（复杂度高，留作后续）。
- 不改 `.venv` 内 browser-use 源码。

## Decisions

### 决策 1：核心手段 = 收紧 `viewport_threshold`（1000 → 200）

这是「恢复设计意图」而非「新造裁剪」，方向天然正确。取 200 保留少量视口外缓冲，避免视口边缘元素被误判不可见；后续可梯度测试 0/500。

- **替代 0（严格视口）**：最省，但视口边缘元素可能被误判、需频繁滚动，风险高。
- **替代 500（更宽）**：降幅有限。

### 决策 2：实现 = 项目层 monkey-patch `DomService.__init__`

新增 `browser_use_ext/dom_patch.py`，在 `DomService.__init__` 之后覆盖 `self.viewport_threshold`（仅当调用方未显式传入时），不依赖 `.venv` 签名细节、升级兼容性好。

- **替代（改 dom_watchdog.py / BrowserProfile 加字段）**：侵入 `.venv`，升级即失效，放弃。
- **替代（在 llm_representation 后裁剪 selector_map）**：需重建 index 映射、易引入点击错位，放弃。

### 决策 3：阈值可配置

新增配置项 `runner.viewport_threshold`（默认 200），runner 透传给 `create_memory_agent`，后者挂载 patch。便于梯度测试与回滚（配置即回滚，无需改代码）。

## Risks / Trade-offs

- **[视口外关键元素不再直接列出 → LLM 需滚动] → 缓解**：browser-use 序列化会加 `more content below viewport - scroll to reveal` 提示，LLM 按提示滚动；验证时关注城市级联面板展开态是否仍在视口内，若失败回退阈值（200→500）。
- **[多滚动 → 调用次数增加 → 总 token 未必下降] → 缓解**：以 profiler 的总 token + 成功率为最终判据，而非单步 DOM 大小；若总 token 不降则调整或放弃。
- **[monkey-patch 与未来 browser-use 升级不兼容] → 缓解**：patch 用 try/except 包裹、失败仅回退默认行为，不影响主流程。

## Migration Plan

- 纯配置 + patch 挂载，无数据迁移、无破坏性变更。
- 回滚：删除 `runner.viewport_threshold` 配置或置回 1000 即可。

## Open Questions

- 最优阈值（0/200/500）需梯度测试确认。
- 若收紧视口后城市级联等多步交互仍失败，是否需要「视口内 + 关键元素白名单」的混合策略（留作方案 B 第二阶段）。
