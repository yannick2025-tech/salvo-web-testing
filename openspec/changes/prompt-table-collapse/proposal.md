## Why

方案 B 第一阶段（`prompt-dom-viewport-cropping`）通过收紧 `viewport_threshold` 到 200 取得了 -6.2% 的降幅，但梯度测试（0/200/1000）证明视口阈值已到极限——0 会导致视口外关键元素被排光、LLM 反复滚动、总 token 反涨 +99%。DOM 的剩余大头是**视口内的表格行**：站点列表 1171 条、订单 204 条（el-table 全量 render），即使只列视口内，仍有几十上百条重复的表格行被序列化进 prompt。这些行对 LLM 是「同质冗余」——用例只需要「确认共 X 条」，无需逐条查看。本 change 识别并折叠这类「大量结构相同的兄弟子树」，只保留前 N 条 + 「共 X 条」提示，是站点列表/订单列表 DOM 膨胀的根本解。

## What Changes

- 新增项目层 monkey-patch（不改 `.venv`），在 `DOMTreeSerializer.serialize_tree` 递归序列化时识别「大量结构相同的兄弟子树」（表格行/列表项），折叠为「前 N 条 + 共 X 条」提示。
- 折叠识别基于结构签名（tag + class + 子节点 tag 序列），仅当相同签名的兄弟数量超过阈值（如 20）时才折叠——避免误伤少量兄弟的导航菜单。
- 保留条数可配置（默认 5），折叠阈值可配置（默认 20）。

## Capabilities

### New Capabilities

- `table-collapse`: 表格/列表折叠——识别 DOM 序列化树中大量结构相同的兄弟子树，折叠为「前 N 条 + 共 X 条」提示，降低大表格/大列表页面的 DOM prompt。

### Modified Capabilities

<!-- 本次为纯新增能力，不改动现有 capability 的 spec 级需求。 -->

## Impact

- **新增文件**：项目层 patch 模块（如 `browser_use_ext/table_collapse.py`）。
- **受影响现有代码**：
  - `browser_use_ext/integration.py`（挂载 patch）
  - `app/config.py` / `config.yaml`（新增折叠阈值与保留条数配置）
  - `app/runner.py`（透传配置）
- **依赖新增**：无。
- **风险**：
  - **误伤导航菜单**（少量结构相似但语义不同的 li）→ 通过「数量阈值」规避（菜单只有几个，表格行有几十上百）。
  - **折叠后 LLM 无法定位特定行**→ 本项目用例只需「确认共 X 条」，不逐行定位；若未来需要定位特定行，可放宽保留条数或关闭折叠。
- **前置结论**（来自 `prompt-dom-viewport-cropping`）：视口裁剪已到极限，折叠是下一步；绝不用「截断到固定字符数」（方案 A 已证有害）。
