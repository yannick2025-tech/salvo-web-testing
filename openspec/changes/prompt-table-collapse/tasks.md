> ⚠️ **本 change 实验失败，代码已回滚**（2026-09-08）。失败原因见文末「实验结果」章节。整体废弃，仅作档案保留，不再实施。

## 1. 配置字段

- [x] 1.1 在 `config.yaml` 新增 `runner.table_collapse` 配置段（已回滚）
- [x] 1.2 在 `app/config.py` 新增 `TableCollapseConfig` 模型（已回滚）

## 2. 折叠 patch 实现

- [x] 2.1 新建 `browser_use_ext/table_collapse.py`，实现结构签名与兄弟分组（已回滚删除）
- [x] 2.2 实现 `patch_table_collapse`：monkey-patch `DOMTreeSerializer.serialize_tree`（已回滚删除）
- [x] 2.3 所有 hook 用 try/except 包裹（已回滚删除）

## 3. 挂载与透传

- [x] 3.1 在 `app/runner.py` 透传 `table_collapse` 配置（已回滚）
- [x] 3.2 在 `create_memory_agent` 挂载 `patch_table_collapse`（已回滚）

## 4. 测试与验证

- [x] 4.1 为折叠逻辑编写单元测试（已随回滚删除）
- [x] 4.2 跑同一用例验证（结果：失败，见下）

## 实验结果（2026-09-08）：失败，已回滚

**核心问题：结构签名「tag + class + 子 tag 序列」无法区分「表格行」和「导航菜单项」——二者结构相同，但语义完全不同。**

| 现象 | 说明 |
|------|------|
| 折叠误伤导航菜单 | 左侧侧边栏菜单（一级项 + 展开二级项）的 `li.el-menu-item` 签名相同、数量超阈值，被一并折叠，LLM 找不到菜单 index 而卡死等待 |
| 破坏翻页用例 | 未来用例可能涉及表格翻页（点下一页），折叠掉表格行会让 LLM 无法理解分页结构、无法定位翻页控件 |

**根因**：仅凭「结构相同」判定「同质冗余」是过拟合的——菜单项、分页表格行都是「结构相同但语义不同」，不能折叠。

**结论**：自动折叠这条路（连同此前的方案 A 简单截断）对 DOM 侧已走到尽头；视口裁剪（`prompt-dom-viewport-cropping`，-6.2%）是 DOM 侧唯一安全有效的优化。剩余 token 大头是 `system + tools` 固定开销（73%，有 prompt caching 兜底），应转向方案 C（精简 system prompt + 工具定义）。
