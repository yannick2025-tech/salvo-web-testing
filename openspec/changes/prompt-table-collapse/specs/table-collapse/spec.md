## ADDED Requirements

### Requirement: 折叠重复表格行

系统 SHALL 在 DOM 序列化时识别「大量结构相同的兄弟子树」（相同 tag + class + 子节点 tag 序列，不含文本），当相同签名的兄弟数量超过阈值时，折叠为「前 N 条 + 共 X 条」提示。

#### Scenario: 大列表折叠

- **WHEN** 页面包含超过阈值的结构相同兄弟（如站点列表 1171 条表格行）
- **THEN** 序列化结果仅包含前 N 条 + 「共 X 条」提示，DOM prompt 显著下降

#### Scenario: 少量兄弟不折叠

- **WHEN** 相同签名的兄弟数量未超过阈值（如导航菜单的几个 li）
- **THEN** 全部保留，不折叠

### Requirement: 折叠可配置

系统 SHALL 支持通过配置指定折叠开关、阈值与保留条数，未指定时用默认值（启用、阈值 20、保留 5）。

#### Scenario: 关闭折叠

- **WHEN** 配置折叠开关为 false
- **THEN** 不挂载折叠 patch，序列化行为与未引入折叠前一致

### Requirement: 保持任务成功率

折叠 SHALL 不降低任务成功率；回归验证同一用例的成功率 SHALL 保持 100%，且 DOM 占比下降。

#### Scenario: 回归验证

- **WHEN** 启用折叠后运行同一用例
- **THEN** 任务成功，DOM 占比下降，且不出现因折叠丢失关键交互元素导致的失败
