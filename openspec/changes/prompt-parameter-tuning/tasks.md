## 1. 配置字段

- [ ] 1.1 在 `config.yaml` 的 `runner` 段新增 `max_clickable_elements_length: 15000` 与 `max_history_items: 10`
- [ ] 1.2 在 `app/config.py` 的 `RunnerConfig` 新增 `max_clickable_elements_length`（默认 15000）与 `max_history_items`（默认 10，`Optional[int]`）字段

## 2. 透传

- [ ] 2.1 在 `app/runner.py` 把 `max_clickable_elements_length`、`max_history_items` 透传给 `create_memory_agent`

## 3. 测试

- [ ] 3.1 编写配置加载测试，验证 `config.yaml` 的 runner 新字段被正确解析进 `RunnerConfig`

## 4. 验证

- [ ] 4.1 跑同一用例（`cases/manhattan/login_and_query.yaml`），用 `PromptUsageProfiler` 对比调参前后的六部分占比
- [ ] 4.2 核对任务成功率保持 100%，DOM 按新上限截断、历史按新条数保留
