# browser-use 元素操作本地记忆 设计文档

> 版本: 1.0 | 日期: 2026-09-04 | 项目: py-web-testing

---

## 1. 背景与目标

### 1.1 现状问题

定制化前端控件（如 Element UI 日期范围选择器、级联选择器等）没有标准 HTML 语义，browser-use 的 LLM 每次都需要多次"试错"才能猜对操作方式。

以用例 1「充电订单管理 → 单据时间」为例：这是一个 Element UI 定制化的日期范围组件，LLM 每次运行都需要重试多次才能正确设置时间。前端类似定制化控件非常多。

### 1.2 目标

设计一套本地记忆机制，让 browser-use 每次尝试后记下成功的操作方式，下一次遇到相同元素时优先复用记忆，跳过试错。

### 1.3 技术栈

| 项 | 值 |
|----|-----|
| browser-use 版本 | 0.13.10 |
| 浏览器协议 | CDP（Chrome DevTools Protocol） |
| LLM | DeepSeek（纯文本，无视觉） |
| 存储方案 | JSON 文件（开源免费） |
| 扩展方式 | Agent 回调 + 自定义 Tool，不修改 browser-use 源码 |

---

## 2. browser-use 元素定位原理

browser-use 的元素定位**不是传统 CSS 选择器/XPath**，而是 **DOM 树索引机制**：

```
1. buildDomTree.js 注入页面 → 递归遍历 DOM
2. 过滤可交互元素（button/input/a/cursor:pointer 等）
3. 为每个元素分配递增索引 [1] [2] [3]...
4. 生成极简文本: [8]<textarea 搜索;false;q;combobox;Google 搜索/>
5. LLM 输出索引号 → Agent 通过 selector_map 找到 XPath 执行操作
```

每个索引条目包含：**标签类型 + 关键属性（placeholder/name）+ ARIA role + 文本内容**。

记忆系统需要匹配的是这些**语义特征**，而非 CSS 选择器。

---

## 3. 数据模型

### 3.1 记忆条目结构

每条记忆 = 一个元素的操作经验：

```json
{
    "version": "1.0",
    "memories": [
        {
            "id": "mem_001",
            "created_at": "2026-09-04T10:30:00",
            "updated_at": "2026-09-04T10:30:00",
            "success_count": 3,
            "last_used_at": "2026-09-04T14:20:00",

            "key": {
                "mode": "flat",
                "flat_key": "订单管理 > 充电订单管理 > 单据时间下拉框",
                "hierarchical_path": ["订单管理", "充电订单管理", "单据时间下拉框"]
            },

            "element_signature": {
                "tag": "div",
                "role": "combobox",
                "aria_label": "单据时间",
                "text_fragments": ["账单生成时间", "订单创建时间"],
                "class_fragments": ["el-select", "el-input"],
                "attributes": {
                    "placeholder": "请选择"
                }
            },

            "operation_steps": [
                {
                    "step": 1,
                    "description": "点击单据时间下拉框 trigger",
                    "action": "click",
                    "target_hint": "el-select 的 .el-input 区域",
                    "element_signature": {
                        "tag": "input",
                        "class_fragments": ["el-input__inner"],
                        "role": "combobox"
                    }
                },
                {
                    "step": 2,
                    "description": "在下拉列表中选择「订单创建时间」",
                    "action": "click_option",
                    "target_hint": "下拉列表中 text=订单创建时间 的选项",
                    "element_signature": {
                        "tag": "li",
                        "class_fragments": ["el-select-dropdown__item"],
                        "text": "订单创建时间"
                    }
                },
                {
                    "step": 3,
                    "description": "点击开始日期输入框",
                    "action": "click",
                    "target_hint": "开始日期 el-date-editor",
                    "element_signature": {
                        "tag": "input",
                        "class_fragments": ["el-range-input"],
                        "placeholder": "开始日期"
                    }
                }
            ],

            "context": {
                "url_pattern": "*/ChargeOrderManagement*",
                "page_title_fragment": "充电订单管理"
            }
        }
    ]
}
```

### 3.2 ElementSignature 模型

基于 browser-use 的 DOM 索引机制，记忆中存储的元素特征与 LLM 看到的 DOM 文本一致：

```python
@dataclass
class ElementSignature:
    tag: str                        # HTML 标签名
    role: Optional[str]             # ARIA role
    aria_label: Optional[str]       # aria-label 属性
    text_fragments: List[str]       # 元素文本片段（用于模糊匹配预留）
    class_fragments: List[str]      # CSS class 片段（不含动态 hash 部分）
    attributes: Dict[str, str]      # 其他关键属性（placeholder, name 等）
```

---

## 4. KEY 设计

### 4.1 设计原则

- **不使用 URL 作 KEY**：URL 不具备通用性（可能含动态参数、不同环境不同域名）
- **使用菜单层级路径**：一级菜单 > 二级菜单 > ... > 页面 > 元素名称，通过菜单路径定位是唯一的
- **两种模式都支持，配置文件控制切换**

### 4.2 两种模式

| 模式 | KEY 示例 | 匹配逻辑 | 适用场景 |
|------|---------|---------|---------|
| **flat** | `"订单管理 > 充电订单管理 > 单据时间下拉框"` | 精确字符串匹配 | 菜单路径固定、元素名唯一 |
| **hierarchical** | `["订单管理", "充电订单管理", "单据时间下拉框"]` | 逐层前缀匹配，支持部分匹配 | 菜单层级可能变化、需要模糊定位 |

**当前优先实现 flat 模式**，hierarchical 模式通过配置项切换。

### 4.3 KEY 生成规则

从 Agent 历史中推断菜单路径：

```python
def infer_menu_path(step_history):
    """
    从 Agent 历史中推断当前菜单路径
    规则：
    - 点击侧边栏菜单项 → 一级菜单
    - 点击展开的子菜单项 → 二级菜单
    - 更深层菜单 → 三级菜单
    """
    path = []
    for step in step_history:
        for action in step.actions:
            if action.type == "click" and is_menu_element(action.element):
                path.append(action.element.text)
    return path

def is_menu_element(element):
    """判断元素是否为菜单项"""
    return (
        'menu' in element.class_fragments
        or 'nav' in element.class_fragments
        or 'sidebar' in element.class_fragments
        or element.role in ('menuitem', 'navigation')
        or 'menu' in str(element.xpath).lower()
    )
```

---

## 5. 匹配设计

### 5.1 三种匹配模式（预留接口，先实现精确匹配）

| 模式 | 实现状态 | 说明 |
|------|---------|------|
| `exact` | **当前实现** | 精确字符串匹配 flat_key / 逐层匹配 hierarchical_path |
| `fuzzy` | 预留 | 元素多维特征加权相似度，阈值控制 |
| `semantic` | 预留 | 本地 embedding 模型（sentence-transformers）向量搜索 |

### 5.2 精确匹配规则

```
flat 模式:
  key.flat_key == 当前推断的菜单路径拼接字符串

hierarchical 模式:
  逐层比较 key.hierarchical_path 与当前菜单路径
  每一层都必须匹配
  当前路径可以比记忆路径短（部分匹配）

element_signature 匹配:
  tag 必须一致
  role 不为空时必须一致
  class_fragments 交集比例 >= 0.5
  text_fragments 或 aria_label 任一匹配
```

### 5.3 匹配流程

```
Agent step 开始
  ↓
从 DOM 状态提取当前页面交互元素列表
  ↓
构建当前元素的 element_signature
  ↓
推断当前菜单路径
  ↓
读取 JSON 记忆文件
  ↓
匹配模式判断:
  ├─ flat → 精确匹配 key.flat_key
  └─ hierarchical → 逐层匹配 key.hierarchical_path
  ↓
命中 → 返回 operation_steps
未命中 → 返回空，Agent 正常试错
```

---

## 6. 记忆写入设计

### 6.1 写入策略

**仅成功时写入**。不记录失败教训，保持简单。

### 6.2 写入流程

```
Agent 任务成功完成（register_done_callback）
  ↓
判断任务是否成功（检查 AgentHistory.final_result()）
  ↓
成功 → 遍历 AgentHistory 的步骤历史
  ↓
识别"困难元素"：同一步骤重试 >= min_retry_threshold 的元素
  ↓
为每个困难元素：
  ├─ 构建 element_signature（从 DOM 交互记录提取）
  ├─ 构建 operation_steps（从成功的那次尝试提取操作序列）
  └─ 推断菜单路径 → 生成 KEY
  ↓
写入 JSON 文件（追加或更新已有条目）
  ↓
更新 success_count + last_used_at + updated_at
```

### 6.3 记忆淘汰

当记忆条目数超过 `max_memories` 时，淘汰最旧的条目（按 `last_used_at` 排序）。

---

## 7. LLM 约束机制

### 7.1 核心挑战

记忆查询和写入可以自动化（callback 驱动），但"按记忆操作"需要约束 LLM 行为。

### 7.2 双轨制设计

#### 轨道 1：Prompt 强约束（软约束增强版）

在 `extend_system_message` 中注入高优先级指令：

```
[规则-P0-必须遵守] 元素操作记忆规则：
1. 如果下方出现「元素操作记忆」区块，你 MUST 优先按照记忆中的步骤操作
2. 记忆中的 element_signature 和当前 DOM 元素匹配时，直接执行记忆步骤，不要重新探索
3. 仅当记忆中的元素在 DOM 中找不到时，才回退到自行尝试
4. 按记忆操作成功后，标记该步骤为 done，不重复操作
5. 违反以上规则将导致任务失败
```

记忆注入格式（绑定 DOM 索引）：

```
[元素操作记忆 - 优先执行]
▼ 单据时间下拉框 (匹配当前DOM元素 [15])
  → 步骤1: click 元素[15]  (.el-input__inner, combobox)
  → 步骤2: click 下拉选项 "订单创建时间"
  → 步骤3: click 开始日期输入框
  ✓ 已验证3次 | 最后成功: 2026-09-04
```

#### 轨道 2：自定义 Tool `follow_memory`（中约束）

注册为 Agent 的自定义 tool，LLM 可以主动调用：

```python
async def execute_memory_steps(element_key: str, browser_session, memory_store):
    """按记忆执行操作，成功返回结果，失败返回 None 让 LLM 自行尝试"""
    memory = memory_store.query(element_key)
    if not memory:
        return ActionResult(extracted_content="未找到记忆，请自行操作")

    for step in memory.operation_steps:
        try:
            element = find_element_by_signature(browser_session, step.element_signature)
            if not element:
                return ActionResult(extracted_content=f"记忆步骤{step.step}失败：元素未找到，请自行操作")
            await execute_action(browser_session, step.action, element)
        except Exception as e:
            return ActionResult(extracted_content=f"记忆步骤{step.step}出错：{e}，请自行操作")

    return ActionResult(
        extracted_content=f"已按记忆完成 {element_key} 的 {len(memory.operation_steps)} 步操作",
        is_done=True
    )
```

**约束效果**：
- LLM 调用 `follow_memory` → 自动执行，不依赖 LLM 的每步决策
- 执行失败 → 返回错误信息，LLM 自行尝试
- LLM 不调用 `follow_memory` → 轨道 1 的 prompt 约束兜底

#### 轨道 3（预留）：自动预执行模式（硬约束）

```
Step callback:
  1. 查询记忆 → 命中
  2. 直接通过 CDP 执行记忆中的操作（跳过 LLM 决策）
  3. 将操作结果注入 state.last_result
  4. LLM 进入下一步时，看到操作已完成
  5. 如果预执行失败 → 回退到正常 LLM 模式 + prompt 注入
```

> 风险：callback 中操作 DOM 可能与 Agent 状态管理冲突。留作后续迭代。

---

## 8. 集成设计

### 8.1 整体工作流

```
┌──────────────────────────────────────────────────────┐
│                  Agent Step 循环                      │
│                                                      │
│  new_step_callback:                                  │
│    ├─ 1. 弹窗扫描 → 自动关闭（由弹窗模块负责）       │
│    └─ 2. 记忆查询 → 命中                             │
│         ├─ 注入 prompt 提示（轨道1: 软约束）           │
│         └─ 注册 follow_memory tool 可用（轨道2: 中约束）│
│                                                      │
│  LLM 决策:                                           │
│    ├─ 调用 follow_memory → 自动执行记忆步骤 ✓        │
│    ├─ 按 prompt 提示按记忆步骤操作 → ✓               │
│    ├─ 忽略记忆自行操作 → prompt 约束兜底（弱）       │
│    └─ 记忆执行失败 → 回退自行尝试                    │
│                                                      │
│  done_callback:                                      │
│    └─ 任务成功 → 自动提取操作历史 → 写入记忆 JSON    │
└──────────────────────────────────────────────────────┘
```

### 8.2 集成入口

```python
from browser_use_ext.integration import create_memory_agent

agent = create_memory_agent(
    task=task,
    llm=llm,
    config_path="./memory/config.json",
    # ... 其他原有参数
)
```

---

## 9. 配置项

```json
{
    "element_memory": {
        "enabled": true,
        "storage_path": "./memory/elements.json",
        "key_mode": "flat",
        "match_mode": "exact",
        "max_memories": 1000,
        "auto_learn": true,
        "min_retry_threshold": 2
    }
}
```

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | true | 是否启用本地记忆 |
| `storage_path` | string | "./memory/elements.json" | JSON 记忆文件路径 |
| `key_mode` | string | "flat" | `flat` / `hierarchical` |
| `match_mode` | string | "exact" | `exact`（当前）/ `fuzzy`（预留）/ `semantic`（预留） |
| `max_memories` | int | 1000 | 最大记忆条目数 |
| `auto_learn` | bool | true | 是否自动从成功操作中学习 |
| `min_retry_threshold` | int | 2 | 重试 >=N 次才算"困难元素"，才记录 |

---

## 10. 文件结构

```
py-web-testing/
├── browser_use_ext/
│   ├── __init__.py
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── store.py                     # JSON 读写
│   │   ├── matcher.py                   # 匹配逻辑（exact/fuzzy/semantic）
│   │   └── models.py                    # 数据模型定义
│   └── integration.py                   # Agent 集成（回调+消息注入+tool注册）
├── memory/
│   └── elements.json                    # 元素操作记忆存储
└── docs/
    └── superpowers/specs/
        └── browser-use-element-memory.md  # 本文档
```

---

## 11. 实施计划

| 阶段 | 内容 | 优先级 |
|------|------|--------|
| P0 | `memory/models.py` — 数据模型 | 高 |
| P0 | `memory/store.py` — JSON 读写 | 高 |
| P0 | `memory/matcher.py` — 精确匹配 | 高 |
| P0 | `integration.py` — Agent 回调 + prompt 注入 + tool 注册 | 高 |
| P1 | `uat-login.py` 改造 — 使用 `create_memory_agent` | 高 |
| P2 | `memory/matcher.py` — 模糊匹配（预留接口） | 中 |
| P2 | `memory/matcher.py` — 语义向量匹配（预留接口） | 低 |
| P3 | 轨道 3：自动预执行模式 | 低 |

---

## 12. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| LLM 忽略 prompt 约束不按记忆操作 | 记忆利用率低 | 双轨制（prompt + follow_memory tool）兜底 |
| 前端改版后旧记忆失配 | 误用失效操作 | 精确匹配 + 失败时自动回退 LLM 模式 |
| JSON 文件并发写入冲突 | 数据损坏 | 单进程运行，写入时加文件锁 |
| 记忆文件过大 | 加载慢 | max_memories 限制 + LRU 淘汰 |
| 菜单路径推断不准确 | KEY 不唯一 | 记录 context（url_pattern、page_title）作为辅助验证 |
