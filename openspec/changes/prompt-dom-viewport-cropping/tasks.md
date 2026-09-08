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

## 实验结果（2026-09-08）：成功

| 指标 | 基线(1000) | 方案 B(200) | 变化 |
|------|-----------|-------------|------|
| invocations | 18 | 18 | 持平 |
| total_prompt_tokens | 241,930 | 226,956 | -6.2% |
| total_tokens | 257,662 | 241,697 | -6.2% |
| 成功率 | 2/2 | 2/2 | 持平 ✅ |

单步 DOM 峰值 22,260 → 19,587 chars（-12%）。降幅有限的原因：视口内的表格行仍密集（el-table 全量 render），DOM 大头在视口内而非视口外。后续可梯度测试 `viewport_threshold=0` 或做「大列表折叠」进一步降本。
