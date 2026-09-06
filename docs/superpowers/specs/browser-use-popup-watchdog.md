# browser-use DOM 弹窗自动关闭 设计文档

> 版本: 1.0 | 日期: 2026-09-04 | 项目: py-web-testing

---

## 1. 背景与目标

### 1.1 现状问题

浏览器弹窗干扰 Agent 执行：
- **Chrome 原生弹窗**：保存密码提示、翻译提示等
- **业务自定义弹窗**：公告、通知、升级提示等（Element UI `.el-dialog`、`.el-message-box` 等）

Agent 被弹窗阻塞或误操作弹窗元素，导致流程中断。

### 1.2 目标

检测到任何弹窗即自动关闭，不依赖 LLM 判断。采用**激进策略**：检测即关。

### 1.3 技术栈

| 项 | 值 |
|----|-----|
| browser-use 版本 | 0.13.10 |
| 浏览器协议 | CDP（Chrome DevTools Protocol） |
| 弹窗策略 | aggressive（检测即关） |

---

## 2. 现有能力

browser-use 0.13.10 已内置 `PopupsWatchdog`（位于 `browser_use/browser/watchdogs/popups_watchdog.py`），通过 CDP `Page.javascriptDialogOpening` 事件自动处理 **JS 原生弹窗**（alert/confirm/prompt/beforeunload）。

**但 PopupsWatchdog 不处理 DOM 自定义弹窗**（如 Element UI 的 `.el-dialog`、公告弹窗等）。

### PopupsWatchdog 已覆盖

| 弹窗类型 | 处理方式 |
|----------|---------|
| alert | accept=true（点击 OK） |
| confirm | accept=true（点击 OK） |
| prompt | accept=false（点击 Cancel） |
| beforeunload | accept=true（允许导航） |

### PopupsWatchdog 未覆盖（需要新增处理）

| 弹窗类型 | 示例 |
|----------|------|
| Element UI Dialog | `.el-dialog__wrapper` |
| Element UI MessageBox | `.el-message-box__wrapper` |
| Element UI Overlay | `.el-overlay` |
| Ant Design Modal | `.ant-modal-wrap` |
| Ant Design Message | `.ant-message` |
| 通用 popup/modal/notice | `[class*="popup"]` / `[class*="modal"]` / `[class*="notice"]` |
| fixed 遮罩层 | `position:fixed + z-index>1000` |

---

## 3. 架构设计

### 3.1 新增 BusinessPopupWatchdog

继承 `BaseWatchdog`，遵循 browser-use 的 watchdog 扩展机制。

```
┌─────────────────────────────────────────────────────┐
│                  Agent Step 循环                      │
│                                                     │
│  ┌──────────────┐    ┌───────────────────────────┐  │
│  │ PopupsWatchdog│   │ BusinessPopupWatchdog     │  │
│  │ (内置)        │   │ (新增)                    │  │
│  │ JS原生弹窗    │   │ DOM业务弹窗               │  │
│  └──────────────┘    └───────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

### 3.2 工作流程

```
触发时机:
  1. 每次 Agent step 前（register_new_step_callback）
  2. 页面跳转后（可选：监听 NavigationCompleteEvent）

扫描方式:
  通过 CDP Runtime.evaluate 注入 JS 脚本扫描 DOM

扫描逻辑:
  ├─ 遍历预定义的弹窗选择器列表
  ├─ 额外检测 fixed/absolute 定位 + z-index > 1000 的遮罩层
  ├─ 优先找关闭按钮 → 模拟点击
  └─ 找不到关闭按钮 → element.remove() 删除 DOM

结果:
  ├─ 日志输出: [PopupWatchdog] Dismissed: .el-dialog (公告测试-00001)
  └─ 将关闭的弹窗信息存入 browser_session._closed_popup_messages
```

### 3.3 DOM 弹窗检测规则

#### 选择器列表

```javascript
const POPUP_SELECTORS = [
    // Element UI
    '[role="dialog"]',
    '.el-dialog__wrapper',
    '.el-message-box__wrapper',
    '.el-overlay',
    // Ant Design
    '.ant-modal-wrap',
    '.ant-message',
    // 通用
    '[class*="popup"]',
    '[class*="modal"]',
    '[class*="notice"]',
    '[class*="notification"]',
    '[class*="alert"]',
    '[class*="toast"]',
];
```

#### 关闭按钮选择器

```javascript
const CLOSE_BUTTON_SELECTORS = [
    '[class*="close"]',
    '[aria-label="Close"]',
    '[aria-label="close"]',
    '.el-dialog__closebtn',
    '.el-dialog__headerbtn',
    '.el-message-box__close',
    '.ant-modal-close',
    '[data-dismiss="modal"]',
];
```

#### 遮罩层检测

```javascript
// 检测 fixed/absolute 定位 + z-index > 1000 + 有面积的元素
const allElements = document.querySelectorAll('*');
const overlays = [];
allElements.forEach(el => {
    const style = getComputedStyle(el);
    if (
        (style.position === 'fixed' || style.position === 'absolute') &&
        parseInt(style.zIndex) > 1000 &&
        el.offsetWidth > window.innerWidth * 0.3 &&
        el.offsetHeight > window.innerHeight * 0.3
    ) {
        overlays.push(el);
    }
});
```

### 3.4 关闭策略

```
1. 优先找关闭按钮 → 模拟 click()
2. 找不到关闭按钮 → element.remove()
3. 遮罩层（overlay）同步删除
4. 记录关闭的弹窗信息到日志
```

---

## 4. 配置项

```json
{
    "popup_watchdog": {
        "enabled": true,
        "strategy": "aggressive",
        "custom_selectors": [],
        "whitelist_selectors": [],
        "scan_on_step": true,
        "scan_on_navigation": true,
        "scan_delay_ms": 500,
        "z_index_threshold": 1000,
        "overlay_min_area_ratio": 0.3
    }
}
```

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | true | 是否启用弹窗自动关闭 |
| `strategy` | string | "aggressive" | `aggressive`（检测即关）/ `selective`（白名单模式，预留） |
| `custom_selectors` | list | [] | 用户自定义的弹窗选择器 |
| `whitelist_selectors` | list | [] | 不关闭的选择器（selective 模式用） |
| `scan_on_step` | bool | true | 每步前是否扫描 |
| `scan_on_navigation` | bool | true | 页面跳转后是否扫描 |
| `scan_delay_ms` | int | 500 | 扫描延迟，避免页面未加载完成时误判 |
| `z_index_threshold` | int | 1000 | 遮罩层 z-index 阈值 |
| `overlay_min_area_ratio` | float | 0.3 | 遮罩层面积占视口的最小比例（小于此值不认为是弹窗） |

---

## 5. JS 扫描脚本核心逻辑

```javascript
(function dismissPopups(config) {
    const POPUP_SELECTORS = [
        '[role="dialog"]', '.el-dialog__wrapper', '.el-message-box__wrapper',
        '.el-overlay', '.ant-modal-wrap', '.ant-message',
        '[class*="popup"]', '[class*="modal"]', '[class*="notice"]',
        '[class*="notification"]', '[class*="alert"]', '[class*="toast"]',
    ];
    // 合并用户自定义选择器
    if (config.custom_selectors) {
        POPUP_SELECTORS.push(...config.custom_selectors);
    }

    const CLOSE_BUTTON_SELECTORS = [
        '[class*="close"]', '[aria-label="Close"]', '[aria-label="close"]',
        '.el-dialog__closebtn', '.el-dialog__headerbtn', '.el-message-box__close',
        '.ant-modal-close', '[data-dismiss="modal"]',
    ];

    const dismissed = [];

    // 1. 扫描已知选择器
    for (const selector of POPUP_SELECTORS) {
        // 跳过白名单
        if (config.whitelist_selectors?.some(w => selector.includes(w))) continue;

        const elements = document.querySelectorAll(selector);
        for (const el of elements) {
            if (el.offsetParent === null) continue;  // 不可见则跳过

            // 尝试找关闭按钮
            let closed = false;
            for (const btnSelector of CLOSE_BUTTON_SELECTORS) {
                const btn = el.querySelector(btnSelector);
                if (btn) {
                    btn.click();
                    dismissed.push({ selector, method: 'close_button' });
                    closed = true;
                    break;
                }
            }

            // 找不到关闭按钮则直接删除
            if (!closed) {
                el.remove();
                dismissed.push({ selector, method: 'remove' });
            }
        }
    }

    // 2. 扫描高 z-index 遮罩层
    const zThreshold = config.z_index_threshold || 1000;
    const minAreaRatio = config.overlay_min_area_ratio || 0.3;
    const allElements = document.querySelectorAll('*');
    for (const el of allElements) {
        if (POPUP_SELECTORS.some(s => el.matches(s))) continue;  // 已处理过
        const style = getComputedStyle(el);
        if (
            (style.position === 'fixed' || style.position === 'absolute') &&
            parseInt(style.zIndex) > zThreshold &&
            el.offsetWidth > window.innerWidth * minAreaRatio &&
            el.offsetHeight > window.innerHeight * minAreaRatio
        ) {
            el.remove();
            dismissed.push({ selector: 'overlay', method: 'remove', zIndex: style.zIndex });
        }
    }

    return dismissed;
})({
    custom_selectors: %s,
    whitelist_selectors: %s,
    z_index_threshold: %d,
    overlay_min_area_ratio: %f,
});
```

---

## 6. 文件结构

```
py-web-testing/
├── browser_use_ext/
│   ├── __init__.py
│   ├── watchdogs/
│   │   ├── __init__.py
│   │   └── business_popup_watchdog.py   # DOM 弹窗自动关闭
│   └── integration.py                   # Agent 集成（弹窗扫描回调）
├── memory/
│   └── config.json                      # 配置文件（含弹窗配置）
└── docs/
    └── superpowers/specs/
        └── browser-use-popup-watchdog.md  # 本文档
```

---

## 7. 实施计划

| 阶段 | 内容 | 优先级 |
|------|------|--------|
| P0 | `business_popup_watchdog.py` — 核心扫描+关闭逻辑 | 高 |
| P0 | `integration.py` — 在 Agent step callback 中调用弹窗扫描 | 高 |
| P1 | `config.json` — 配置文件 | 高 |
| P2 | Chrome 原生弹窗启动参数屏蔽（补充 PopupsWatchdog） | 中 |

---

## 8. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| DOM 弹窗误关（如重要业务弹窗） | 业务流程中断 | aggressive 策略可配置 whitelist |
| 页面未加载完成时误判弹窗 | 正常元素被误删 | scan_delay_ms 延迟 + 面积阈值 |
| z-index 阈值过高导致遗漏 | 弹窗未被关闭 | 阈值可配置，默认 1000 |
| element.remove() 后页面布局错乱 | 页面异常 | 优先 click 关闭按钮，remove 是兜底 |
