"""元素记忆匹配逻辑"""

from __future__ import annotations

import logging
from typing import List, Optional, Tuple

from .models import ElementMemory, ElementSignature
from .store import MemoryStore

logger = logging.getLogger(__name__)


class MemoryMatcher:
    """记忆匹配器，支持 exact / fuzzy / semantic 三种模式（当前实现 exact）"""

    def __init__(self, store: MemoryStore, key_mode: str = "flat", match_mode: str = "exact"):
        self.store = store
        self.key_mode = key_mode
        self.match_mode = match_mode

    def match(
        self,
        menu_path: List[str],
        element_signature: Optional[ElementSignature] = None,
    ) -> Optional[ElementMemory]:
        """
        根据菜单路径和元素特征匹配记忆。

        Args:
            menu_path: 当前推断的菜单路径，如 ["订单管理", "充电订单管理", "单据时间下拉框"]
            element_signature: 当前元素特征（可选，用于辅助验证）

        Returns:
            匹配到的 ElementMemory，未匹配返回 None
        """
        if self.match_mode == "exact":
            return self._match_exact(menu_path, element_signature)
        elif self.match_mode == "fuzzy":
            # 预留接口
            logger.warning("fuzzy 匹配模式尚未实现，回退到 exact")
            return self._match_exact(menu_path, element_signature)
        elif self.match_mode == "semantic":
            # 预留接口
            logger.warning("semantic 匹配模式尚未实现，回退到 exact")
            return self._match_exact(menu_path, element_signature)
        else:
            logger.error(f"未知匹配模式: {self.match_mode}")
            return None

    def _match_exact(
        self,
        menu_path: List[str],
        element_signature: Optional[ElementSignature] = None,
    ) -> Optional[ElementMemory]:
        """精确匹配"""
        if self.key_mode == "flat":
            flat_key = " > ".join(menu_path)
            memory = self.store.query_by_flat_key(flat_key)
            if memory and element_signature:
                # 用 element_signature 辅助验证
                if not memory.element_signature.matches(element_signature):
                    logger.debug(f"flat key 匹配但 element_signature 不匹配: {flat_key}")
                    return None
            return memory
        else:
            memory = self.store.query_by_hierarchical_path(menu_path)
            if memory and element_signature:
                if not memory.element_signature.matches(element_signature):
                    logger.debug(f"hierarchical path 匹配但 element_signature 不匹配: {menu_path}")
                    return None
            return memory

    def format_memory_for_prompt(self, memory: ElementMemory) -> str:
        """将记忆格式化为 LLM 可读的提示文本"""
        steps_text = []
        for s in memory.operation_steps:
            step_line = f"  → 步骤{s.step}: {s.action} {s.target_hint}"
            if s.input_value:
                step_line += f" (输入: {s.input_value})"
            if s.element_signature:
                sig_parts = []
                if s.element_signature.class_fragments:
                    sig_parts.append(f".{'.'.join(s.element_signature.class_fragments)}")
                if s.element_signature.role:
                    sig_parts.append(f"role={s.element_signature.role}")
                if s.element_signature.text_fragments:
                    sig_parts.append(f"text={'|'.join(s.element_signature.text_fragments)}")
                if sig_parts:
                    step_line += f" ({', '.join(sig_parts)})"
            steps_text.append(step_line)

        key_str = memory.key.to_flat_string()
        result = (
            f"[元素操作记忆 - 优先执行]\n"
            f"▼ {key_str}\n"
            + "\n".join(steps_text)
            + f"\n  ✓ 已验证{memory.success_count}次 | 最后成功: {memory.last_used_at[:10]}"
        )
        return result
