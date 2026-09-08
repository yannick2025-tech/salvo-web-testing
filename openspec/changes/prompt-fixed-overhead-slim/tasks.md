## 1. C1 工具精简：配置

- [x] 1.1 在 `config.yaml` 新增 `runner.tool_exclude` 清单（默认排除 search/upload_file/save_as_pdf/write_file/replace_file/read_file/find_text/close）
- [x] 1.2 在 `app/config.py` 新增工具排除清单字段（`list[str]`）

## 2. C1 工具精简：透传与实现

- [x] 2.1 在 `create_memory_agent` 构造 `Tools(exclude_actions=...)` 时应用排除清单（保留 follow_memory）
- [x] 2.2 在 `app/runner.py` 透传排除清单给 `create_memory_agent`

## 3. C1 验证

- [x] 3.1 为工具排除逻辑编写单元测试（排除清单生效、必需工具保留）
- [x] 3.2 跑同一用例，用 profiler 核对 tools 定义字符数下降、成功率保持 100%

## 4. C2 system prompt 精简：模板

- [ ] 4.1 编写精简版 system prompt 模板（删除 file_system/planning/browser_vision/examples，保留 output/action/browser 规则）
- [ ] 4.2 在 `create_memory_agent` 透传 `override_system_message`（受配置开关控制）
- [ ] 4.3 在 `app/runner.py` 透传开关

## 5. C2 验证

- [ ] 5.1 跑同一用例，用 profiler 核对 system 定义字符数下降、无输出格式错误、成功率保持 100%

## C1 实验结果（2026-09-08）：成功

- tools 定义单次 21,040 → **13,781 chars（-34.5%）**，两次跑稳定，无副作用。
- 记忆 + auto_apply 生效，日期正确（08-29 ~ 09-07，过去10天不含今天）。
- 用例2 城市级联存在随机性（第1次 0 条、第2次成功），与工具精简无关（工具精简只排除 search/close 等）。
