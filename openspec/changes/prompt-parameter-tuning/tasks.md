> ⚠️ **本 change 实验失败，代码已回滚**（详见 `design.md`「实验结果」章节）。以下任务均曾实施，但验证结论为失败（total_tokens +137%、用例2失败），故整体废弃，仅作档案保留，不再实施。

## 1. 配置字段

- [x] 1.1 在 `config.yaml` 的 `runner` 段新增 `max_clickable_elements_length: 15000` 与 `max_history_items: 10`（已回滚）
- [x] 1.2 在 `app/config.py` 的 `RunnerConfig` 新增字段（已回滚）

## 2. 透传

- [x] 2.1 在 `app/runner.py` 透传（已回滚）

## 3. 测试

- [x] 3.1 编写配置加载测试（已随回滚删除）

## 4. 验证

- [x] 4.1 跑同一用例对比（结果：失败，invocations 18→40、total_tokens +137%）
- [x] 4.2 核对成功率保持 100%（结果：未保持，用例2城市级联失败）
