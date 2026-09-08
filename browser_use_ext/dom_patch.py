"""DOM 视口裁剪 patch：收紧 browser-use 的 viewport_threshold。

browser-use 的 `DomService.viewport_threshold` 默认 1000（视口底部往下 1000px
内的元素也算可见），导致大列表页面大量视口外记录被列入 selector_map、DOM
序列化膨胀。本模块通过 monkey-patch 把该阈值收紧为配置值，恢复「只列视口内
元素」的设计意图。

纯项目层 patch，不修改 .venv 内源码；所有操作用 try/except 保护，失败仅记录
日志、不影响主流程。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def patch_viewport_threshold(threshold: int) -> None:
    """把 DomService 的 viewport_threshold 默认值收紧为 threshold。

    仅在调用方未显式传入 `viewport_threshold` 时覆盖默认值；幂等（重复调用只
    更新阈值）。
    """
    try:
        from browser_use.dom.service import DomService
    except Exception as e:  # noqa: BLE001 —— patch 失败不影响主流程
        logger.debug(f"[dom_patch] 导入 DomService 失败: {e}")
        return

    try:
        # 幂等：已 patch 则只更新阈值
        if getattr(DomService, "_viewport_patched", False):
            DomService._viewport_threshold_override = threshold
            return

        _orig_init = DomService.__init__

        def _patched_init(self, *args, **kwargs):
            _orig_init(self, *args, **kwargs)
            if "viewport_threshold" not in kwargs:
                self.viewport_threshold = getattr(
                    DomService, "_viewport_threshold_override", threshold
                )

        DomService.__init__ = _patched_init
        DomService._viewport_threshold_override = threshold
        DomService._viewport_patched = True
        logger.info(f"[dom_patch] 已收紧 viewport_threshold 为 {threshold}")
    except Exception as e:  # noqa: BLE001
        logger.debug(f"[dom_patch] patch 失败: {e}")
