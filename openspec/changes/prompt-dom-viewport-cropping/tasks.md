## 1. 配置字段

- [x] 1.1 在 `config.yaml` 的 `runner` 段新增 `viewport_threshold: 200`
- [x] 1.2 在 `app/config.py` 的 `RunnerConfig` 新增 `viewport_threshold`（默认 200，`Optional[int]`）字段

## 2. patch 实现

- [x] 2.1 新建 `browser_use_ext/dom_patch.py`，实现 `patch_viewport_threshold(threshold)`：monkey-patch `DomService.__init__`，仅当调用方未显式传 `viewport_threshold` 时覆盖为配置值
- [x] 2.2 所有 hook 用 try/except 包裹，patch 失败仅回退默认行为、不影响主流程

## 3. 挂载与透传

- [x] 3.1 在 `app/runner.py` 透传 `viewport_threshold` 给 `create_memory_agent`
- [x] 3.2 在 `create_memory_agent` 按配置挂载 `patch_viewport_threshold`

## 4. 测试与验证

- [x] 4.1 为 `patch_viewport_threshold` 编写单元测试（验证 DomService 实例阈值被覆盖、不侵入源码）
- [x] 4.2 跑同一用例（`cases/manhattan/login_and_query.yaml`），用 profiler 对比 DOM 占比与总 token，核对成功率保持 100%

## 实验结果（2026-09-08）：成功，且 200 为最优点

梯度测试三个阈值（同一用例）：

| viewport_threshold | invocations | total_tokens | 成功率 | 结论 |
|-------------------|------------|-------------|--------|------|
| 1000（browser-use 默认） | 18 | 257,662 | 2/2 | 基线 |
| **200** | **18** | **241,697** | **2/2** | ✅ **最优点（-6.2%）** |
| 0 | 39 | 481,593 | 2/2 | ❌ 太激进（+99%） |

- `200`：单步 DOM 峰值 22,260 → 19,587 chars（-12%），成功率不变、无重试。
- `0`：视口外的关键元素被排光，LLM 反复滚动查找（订单列表页 17 步才推进），调用次数 18→39、总 token 反涨近一倍。

**结论**：`viewport_threshold=200` 是当前最优；继续降本需转向「大列表折叠」（视口内元素仍密集，无法靠视口阈值进一步压缩）。
