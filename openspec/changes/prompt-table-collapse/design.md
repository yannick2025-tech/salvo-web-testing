## Context

方案 B 第一阶段（`prompt-dom-viewport-cropping`）把 `viewport_threshold` 收紧到 200，取得 -6.2%，但梯度测试证明视口阈值已到极限（0 反涨 +99%）。DOM 剩余大头是视口内的表格行（站点列表 1171 条、订单 204 条，el-table 全量 render）。DOM 序列化入口是 `DOMTreeSerializer.serialize_tree(node, include_attributes, depth)`（静态方法，递归遍历 `SimplifiedNode` 树），每个 `SimplifiedNode` 有 `original_node`（tag/attributes/text）与 `children`。

## Goals / Non-Goals

**Goals:**

- 识别并折叠「大量结构相同的兄弟子树」（表格行/列表项），只保留前 N 条 + 「共 X 条」提示，降低大列表页面 DOM prompt。
- 保持成功率 100%，不误伤导航菜单等少量语义兄弟。
- 用 profiler 量化 DOM 占比下降与总 token 变化。

**Non-Goals:**

- 不做「截断到固定字符数」（方案 A 已证有害）。
- 不改 `.venv` 内 browser-use 源码。
- 不做「按文本语义识别具体行」（如按站点名定位），本阶段仅按结构折叠。

## Decisions

### 决策 1：hook 点 = monkey-patch `DOMTreeSerializer.serialize_tree`

在递归序列化前对 `node.children` 做折叠，再交还原方法序列化。递归调用会自然走 patched 版本，每层都能折叠。

- **替代（patch llm_representation）**：拿不到树结构，放弃。
- **替代（改 serializer）**：侵入 `.venv`，放弃。

### 决策 2：折叠识别 = 结构签名（tag + class + 子 tag 序列，不含文本）

表格行的文本各异（不同站点名），但 tag/class/列结构相同；导航菜单 li 的 class 或数量不同。故签名用 `(tag_name, class, 子节点 tag 序列)`，**故意不含文本**——这样表格行（文本不同）被归入同组折叠，而少量语义兄弟因数量不足阈值不受影响。

### 决策 3：折叠阈值 = 20（相同签名兄弟数）

仅当相同签名的兄弟数量 > 20 时才折叠。导航菜单通常 < 20 个 li，不受影响；表格行几十上百条，触发折叠。

### 决策 4：保留条数 = 5（前 5 条 + 「共 X 条」提示）

LLM 只需「确认共 X 条」，保留前 5 条足够其理解列表结构；折叠说明以文本节点插入被折叠位置附近。

### 决策 5：配置化

新增 `runner.table_collapse` 配置（`enabled`/`threshold`/`keep`），默认开启，便于回滚与调参。

## Risks / Trade-offs

- **[误伤导航菜单（少量结构相似但语义不同的 li）] → 缓解**：数量阈值 20 兜底；若仍误伤，可把菜单容器（nav/sidebar class）加入白名单不折叠。
- **[折叠后无法定位特定行] → 缓解**：本项目用例只需「确认共 X 条」；若未来需要定位特定行，放宽 keep 或关闭折叠。
- **[签名碰撞导致误折叠] → 缓解**：签名含 class + 子 tag 序列，碰撞概率低；上线前用 profiler 对比 + 成功率回归。

## Migration Plan

- 纯配置 + patch 挂载，无数据迁移。
- 回滚：置 `runner.table_collapse.enabled=false` 即可。

## Open Questions

- 阈值 20 / 保留 5 是否最优，需跑用例后按 profiler 与成功率梯度调整。
- 是否需要「菜单容器白名单」以彻底规避误伤（首版先不做，遇误伤再加）。
