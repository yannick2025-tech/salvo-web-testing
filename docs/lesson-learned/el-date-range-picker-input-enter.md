# Lesson Learned：Element UI 日期范围控件（el-date-range-picker）设值调试实录

- **日期**：2026-09-06
- **场景**：browser-use（0.13.10）+ DeepSeek 自动执行"充电订单管理 → 单据时间设为 2026-09-04"用例，LLM 始终无法通过自身 `input` 工具给日期控件设值，反复失败。
- **核心教训**：Element UI 日期范围选择器的 `<input class="el-range-input">` 只是"展示层"，**直接赋 `.value` 会被控件内部逻辑回退**。必须用**原生 value setter + input 事件 + Enter 回车**才能让 Vue/控件认可，从而真正生效。
- **方法论教训**：对"自定义/框架控件"不要凭 DOM 印象写定位代码，应**在真实页面的 DevTools Console 里分步实测**，先探明结构、再验证最小可行操作，最后才固化成可复用脚本/记忆。

---

## 背景

用例要求在"充电订单管理"页把**单据时间范围**设成单日 `2026-09-04`。Agent 日志显示 LLM 反复尝试：

1. 用 browser-use `input` 填 `2026-09-04` → 被回退，值仍显示 `2026-08-31 ~ 2026-09-06`。
2. 填完整 `2026-09-04 00:00:00` / `2026-09-04 23:59:59` → 仍被回退。
3. 尝试 `evaluate` 找日历面板 `.el-picker-panel` 点选 → 找不到/点错。
4. 日志一度误判"input 在 shadow DOM 里"。

最终任务在 DeepSeek **HTTP 402（余额不足）** 时被强制终止，`final_result=None`，记忆未写入。

> 这段"反复失败"恰好说明这类控件正是**值得记忆**的目标——它无法靠 LLM 通用行为完成，必须靠精确脚本。

---

## 目标控件的一段真实 HTML

```html
<input tabindex="0" autocomplete="off" role="combobox"
       aria-haspopup="dialog" placeholder="开始时间"
       class="el-range-input" value="2026-09-02 02:09:04">
```

- `class="el-range-input"`，同组通常还有一个 `placeholder="结束时间"` 的兄弟 input。
- 属于 Element UI 的 `el-date-picker`（type=`daterange`）。

---

## 调试过程（逐步 Console 实测）

> Chrome Console 首次粘贴会提示 `allow pasting`，先输入 `allow pasting` 回车。

### 第 1 步：尝试按"文本含开始时间"定位容器 —— ❌

```js
const ed=[...document.querySelectorAll('.el-range-editor')]
  .find(e=>(e.textContent||'').includes('开始时间'));
ed.querySelector('input').click();   // 报错
```

**现象**：`ed` 为 `undefined`，报 `Cannot read properties of undefined (reading 'querySelector')`。

**结论/教训**：`textContent.includes('开始时间')` 在这种复合控件上不可靠；不要依赖容器文本，改用**确定的 class + placeholder** 定位。

### 第 2 步：探明页面控件结构 —— ✅ 关键信息

```js
(async function(){
  const log=[];
  log.push('URL: '+location.href);
  log.push('input[placeholder含开始] 数: '+
    [...document.querySelectorAll('input')]
      .filter(i=>(i.placeholder||'').includes('开始')||(i.getAttribute('aria-label')||'').includes('开始')).length);
  log.push('.el-range-editor 数: '+document.querySelectorAll('.el-range-editor').length);
  log.push('.el-range-input 数: '+document.querySelectorAll('.el-range-input').length);
  log.push('el-range-input 在 shadow 内数量: '+
    [...document.querySelectorAll('.el-range-input')]
      .filter(i=>i.getRootNode&&i.getRootNode()!==document).length);
  console.log(log.join('\n'));
})();
```

**现象**：
```
.el-range-editor 数: 1
.el-range-input 数: 2
el-range-input 在 shadow 内数量: 0
```

**结论**：
- 页面**只有 1 组**日期范围控件（`.el-range-editor` = 1），2 个 `el-range-input`（开始/结束）。
- **不在 shadow DOM**（shadow 内数量 = 0）——之前的"shadow DOM"判断是错的。

### 第 3 步：点开面板，确认日历表格结构 —— ✅

```js
(async function(){
  const inputs=[...document.querySelectorAll('input.el-range-input')];
  inputs[0].click();                     // 打开"开始时间"
  await new Promise(r=>setTimeout(r,700));
  console.log([
    '点击后 .el-picker-panel 数: '+document.querySelectorAll('.el-picker-panel').length,
    '.el-date-range-picker 数: '+document.querySelectorAll('.el-date-range-picker').length,
    '.el-date-table 数: '+document.querySelectorAll('.el-picker-panel .el-date-table').length,
  ].join('\n'));
})();
```

**现象**：点开后出现 1 个 `.el-picker-panel` / `.el-date-range-picker`，内含 **2 个 `.el-date-table`**（左=前月，右=后月）。

**结论**：日历面板由 popper 挂到 body，**不在 shadow**。但因 daterange 默认横跨两个月（8/31~9/6），目标日 9/4 落在哪张表、表格里含跨月占位"4"（8/4、9/4 各一个）**极易点错**。

### 第 4 步：尝试"点日历单元格设 9/4" —— ❌（选错月/不生效）

试过两版"找文本为 4 的 td 点它"，返回 `true` 但 `value` **始终不变**：

```
点 4(开始): true
开始value=2026-08-31 00:00:00 结束value=2026-09-06 23:59:59   ← 没变
最终   开始value=2026-08-31 00:00:00 结束value=2026-09-06 23:59:59
```

**现象**：dump 两张表的可用日序列后看到，每张表都有**多个文本为 "4" 的 td**（前月/当月/后月占位混排），`find` 命中第一个"4" = 错误月份的占位格，点击不被 Element UI 当作有效选择。

**结论/教训**：`daterange` 点日历要设单日**极易点错月份**，且"文本==day"的定位有歧义；这条路**不稳定**，弃用，改走"输入+回车"（Element UI 官方支持的手动输入）。

### 第 5 步：验证"手动输入 + Enter" —— ✅ 成功（决定性）

```js
(async function(){
  const inputs=[...document.querySelectorAll('input.el-range-input')];
  function typeAndEnter(input, text){
    const proto = input instanceof HTMLInputElement
      ? HTMLInputElement.prototype : HTMLTextAreaElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(proto,'value').set; // 原生 setter!
    setter.call(input,'');  input.dispatchEvent(new Event('input',{bubbles:true}));
    setter.call(input,text); input.dispatchEvent(new Event('input',{bubbles:true}));
    input.focus();
    input.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',code:'Enter',bubbles:true,cancelable:true}));
    input.dispatchEvent(new KeyboardEvent('keyup',{key:'Enter',code:'Enter',bubbles:true}));
    input.dispatchEvent(new Event('change',{bubbles:true}));
  }
  inputs[0].focus(); typeAndEnter(inputs[0],'2026-09-04');
  await new Promise(r=>setTimeout(r,400));
  inputs[1].focus(); typeAndEnter(inputs[1],'2026-09-04');
  await new Promise(r=>setTimeout(r,500));
  console.log('开始value='+inputs[0].value+' 结束value='+inputs[1].value
              +' aria-expanded(0)='+inputs[0].getAttribute('aria-expanded'));
})();
```

**现象**（成功）：
```
开始value=2026-09-04  结束value=2026-09-04  aria-expanded=false
```

**结论（最终方案）**：
- 关键在于用**原生 value setter**（触发 Vue 识别）+ 派发 `input` + `keydown Enter`（触发 Element UI 确认解析）+ `change`。
- browser-use 的 `input` 工具之所以失败，就是它只做了 `.value=` + 普通 input 事件，**缺少 Enter 确认**，被控件回退。

---

## 沉淀为代码 / 记忆

1. `integration._build_find_and_act_js` 新增 **`action="input_enter"`** 分支：生成上述"原生 setter + input + Enter + change"的 JS，命中所有 `input.el-range-input`（开始/结束都设）。
2. `follow_memory` 支持 **`@today@` / `@now@`** 令牌，执行时替换为当天日期（跨天通用）。
3. 已把一条**种子记忆**写入 `memory/elements.json`：

   ```
   key : 订单管理 > 充电订单管理 > 单据时间-日期范围设置
   action: input_enter | value: 2026-09-04
   ```

---

## 经验总结（可复用 Checklist）

1. **先探结构，再写脚本**：对框架自定义控件，先在真实页面 Console 用**只读**探针确认——是否 shadow DOM？容器/输入框的确定 class？页面是否只有一组该控件？
2. **`textContent.includes(...)` 定位不可靠**，优先 `class` + `placeholder` + `aria-label`。
3. **`daterange` 点日历设单日极易选错月**（跨月占位 cell 文本重复），除非能精确定位到"目标月份的那张表、那一个 td"，否则不稳定。
4. **框架控件"直接赋 `.value`"通常无效**，需触发它内部认可的事件链（此处是原生 setter + input + Enter/change）。
5. **把"验证过的最小可执行操作"固化为记忆/脚本**，让每次运行跳过 LLM 试错（越跑越快）。
6. 调试后把**每步试错与结论**及时落成 lesson-learned 文档，供后续类似控件复用。
