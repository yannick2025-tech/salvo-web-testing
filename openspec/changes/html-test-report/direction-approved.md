# 方向选择记录（Direction Approved）

## 背景

用户对报告的内容结构（元信息 + 指标 + 多平台分组 + 用例折叠）满意，要求用 huashu-design 重新设计「样式」，体现年轻化、互联网化。

## 展示的三版真实初稿

| 方向 | 视觉语言 | 文件 |
|---|---|---|
| A · Fresh | 清新活力（大圆角 + 柔和渐变卡片 + 圆环通过率） | `_report_design_demo/index.html`（view-a） |
| B · Glass | 未来玻璃（渐变底 + 玻璃拟态 + 发光状态） | `_report_design_demo/index.html`（view-b） |
| C · Editorial | 编辑科技（衬线大标题 + 细线分隔 + 大数字横排） | `_report_design_demo/index.html`（view-c） |

三版内容结构完全一致，仅视觉语言不同；截图均为占位色块（真实截图待真实运行后产生）。

## 用户选择原话

> 「用C吧」

即选定 **C · Editorial（编辑科技）** 方向。

## 后续动作

- 将 C 方向视觉规范落地到 `app/report/render.py`（字体用系统栈保证离线可用）。
- 数据模型升级为「元信息 + 多平台分组 + 用例折叠」结构（见 design.md 决策 9）。
