"""业务 DOM 弹窗自动关闭

通过 CDP Runtime.evaluate 注入 JS 扫描 DOM，自动关闭自定义弹窗。
browser-use 内置的 PopupsWatchdog 只处理 JS 原生弹窗（alert/confirm/prompt），
此模块处理 DOM 自定义弹窗（Element UI Dialog、Ant Design Modal 等）。
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from ..memory.models import PopupWatchdogConfig

logger = logging.getLogger(__name__)

# JS 扫描脚本模板
POPUP_SCAN_JS = """
(async function dismissPopups(config) {
    const POPUP_SELECTORS = [
        '[role="dialog"]',
        '.el-dialog__wrapper',
        '.el-message-box__wrapper',
        '.el-overlay',
        '.ant-modal-wrap',
        '.ant-message',
        '[class*="popup"]',
        '[class*="modal"]',
        '[class*="notice"]',
        '[class*="notification"]',
        '[class*="alert"]',
        '[class*="toast"]',
    ];

    // 合并用户自定义选择器
    if (config.custom_selectors && config.custom_selectors.length > 0) {
        POPUP_SELECTORS.push(...config.custom_selectors);
    }

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

    const dismissed = [];
    const whitelist = config.whitelist_selectors || [];

    // 1. 扫描已知选择器
    for (const selector of POPUP_SELECTORS) {
        // 跳过白名单
        if (whitelist.some(w => selector.includes(w))) continue;

        try {
            const elements = document.querySelectorAll(selector);
            for (const el of elements) {
                if (el.offsetParent === null && el.offsetWidth === 0) continue;  // 不可见则跳过

                // 尝试找关闭按钮
                let closed = false;
                for (const btnSelector of CLOSE_BUTTON_SELECTORS) {
                    const btn = el.querySelector(btnSelector);
                    if (btn) {
                        btn.click();
                        dismissed.push({ selector: selector, method: 'close_button', text: el.textContent?.substring(0, 50) });
                        closed = true;
                        break;
                    }
                }

                // 找不到关闭按钮则直接删除
                if (!closed) {
                    el.remove();
                    dismissed.push({ selector: selector, method: 'remove', text: el.textContent?.substring(0, 50) });
                }
            }
        } catch (e) {
            // 选择器可能无效，跳过
        }
    }

    // 2. 扫描高 z-index 遮罩层
    const zThreshold = config.z_index_threshold || 1000;
    const minAreaRatio = config.overlay_min_area_ratio || 0.3;
    try {
        const allElements = document.querySelectorAll('*');
        for (const el of allElements) {
            // 跳过已处理的选择器
            try {
                if (POPUP_SELECTORS.some(s => el.matches(s))) continue;
            } catch(e) {}

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
    } catch (e) {
        // 忽略错误
    }

    return JSON.stringify(dismissed);
})({
    custom_selectors: %s,
    whitelist_selectors: %s,
    z_index_threshold: %d,
    overlay_min_area_ratio: %f,
});
"""


class BusinessPopupWatchdog:
    """DOM 弹窗自动关闭"""

    def __init__(self, config: PopupWatchdogConfig):
        self.config = config
        self._dismissed_log: List[Dict[str, Any]] = []

    async def scan(self, browser_session: Any) -> List[Dict[str, Any]]:
        """
        扫描并关闭 DOM 弹窗。

        Args:
            browser_session: browser-use 的 BrowserSession 实例

        Returns:
            关闭的弹窗列表
        """
        if not self.config.enabled:
            return []

        try:
            # 获取 CDP session
            cdp_session = await browser_session.get_or_create_cdp_session(
                target_id=browser_session.agent_focus_target_id, focus=False
            )

            # 注入 JS 扫描脚本
            js_script = POPUP_SCAN_JS % (
                json.dumps(self.config.custom_selectors),
                json.dumps(self.config.whitelist_selectors),
                self.config.z_index_threshold,
                self.config.overlay_min_area_ratio,
            )

            result = await cdp_session.cdp_client.send.Runtime.evaluate(
                params={"expression": js_script, "returnByValue": True},
                session_id=cdp_session.session_id,
            )

            # 解析结果
            dismissed = []
            if result and "result" in result:
                result_value = result["result"]
                if isinstance(result_value, dict) and "value" in result_value:
                    try:
                        dismissed = json.loads(result_value["value"])
                    except (json.JSONDecodeError, TypeError):
                        pass

            # 记录日志
            for item in dismissed:
                method = item.get("method", "unknown")
                selector = item.get("selector", "unknown")
                text = item.get("text", "")[:30]
                logger.info(f"[PopupWatchdog] Dismissed: {selector} ({method}) text={text}")
                self._dismissed_log.append(item)

            return dismissed

        except Exception as e:
            logger.debug(f"弹窗扫描失败（页面可能未加载完成）: {e}")
            return []

    def get_dismissed_log(self) -> List[Dict[str, Any]]:
        """获取本次运行中关闭的弹窗日志"""
        return self._dismissed_log
