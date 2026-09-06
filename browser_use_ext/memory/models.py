"""元素操作记忆数据模型"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ElementSignature(BaseModel):
    """元素定位特征，基于 browser-use 的 DOM 索引机制"""

    tag: str = Field(description="HTML 标签名")
    role: Optional[str] = Field(default=None, description="ARIA role")
    aria_label: Optional[str] = Field(default=None, description="aria-label 属性")
    text_fragments: List[str] = Field(default_factory=list, description="元素文本片段")
    class_fragments: List[str] = Field(default_factory=list, description="CSS class 片段")
    attributes: Dict[str, str] = Field(default_factory=dict, description="其他关键属性")

    def matches(self, other: ElementSignature, class_overlap_threshold: float = 0.5) -> bool:
        """判断两个 ElementSignature 是否匹配（精确匹配规则）"""
        # tag 必须一致
        if self.tag != other.tag:
            return False

        # role 不为空时必须一致
        if self.role and other.role and self.role != other.role:
            return False

        # class_fragments 交集比例 >= 阈值
        if self.class_fragments and other.class_fragments:
            overlap = len(set(self.class_fragments) & set(other.class_fragments))
            ratio = overlap / max(len(set(self.class_fragments)), len(set(other.class_fragments)))
            if ratio < class_overlap_threshold:
                return False

        # text_fragments 或 aria_label 任一匹配
        text_match = False
        if self.text_fragments and other.text_fragments:
            for t1 in self.text_fragments:
                for t2 in other.text_fragments:
                    if t1 and t2 and (t1 in t2 or t2 in t1):
                        text_match = True
                        break
        if self.aria_label and other.aria_label:
            if self.aria_label in other.aria_label or other.aria_label in self.aria_label:
                text_match = True

        # 如果 class 已匹配，text 不是必须的
        if self.class_fragments and other.class_fragments:
            return True

        # 如果没有 class，text 必须匹配
        return text_match


class OperationStep(BaseModel):
    """操作步骤"""

    step: int = Field(description="步骤序号")
    description: str = Field(description="步骤描述")
    action: str = Field(description="动作类型: click / input / select / click_option")
    target_hint: str = Field(default="", description="目标元素提示")
    element_signature: Optional[ElementSignature] = Field(
        default=None, description="目标元素特征"
    )
    input_value: Optional[str] = Field(default=None, description="输入值（input 动作时）")


class MemoryKey(BaseModel):
    """记忆 KEY，支持 flat 和 hierarchical 两种模式"""

    mode: str = Field(default="flat", description="flat | hierarchical")
    flat_key: str = Field(default="", description="flat 模式的完整 KEY 字符串")
    hierarchical_path: List[str] = Field(
        default_factory=list, description="hierarchical 模式的层级路径"
    )

    def to_flat_string(self) -> str:
        """转换为 flat 字符串"""
        if self.mode == "flat" and self.flat_key:
            return self.flat_key
        return " > ".join(self.hierarchical_path)


class MemoryContext(BaseModel):
    """记忆上下文，辅助验证"""

    url_pattern: Optional[str] = Field(default=None, description="URL 模式（辅助验证）")
    page_title_fragment: Optional[str] = Field(default=None, description="页面标题片段（辅助验证）")


class ElementMemory(BaseModel):
    """元素操作记忆条目"""

    id: str = Field(default_factory=lambda: f"mem_{uuid.uuid4().hex[:8]}")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    success_count: int = Field(default=1, description="成功次数")
    last_used_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    key: MemoryKey = Field(description="记忆 KEY")
    element_signature: ElementSignature = Field(description="元素定位特征")
    operation_steps: List[OperationStep] = Field(description="操作步骤列表")
    context: MemoryContext = Field(default_factory=MemoryContext, description="上下文")

    def touch(self) -> None:
        """更新使用时间"""
        self.last_used_at = datetime.now().isoformat()
        self.updated_at = datetime.now().isoformat()
        self.success_count += 1


class MemoryFile(BaseModel):
    """记忆 JSON 文件结构"""

    version: str = Field(default="1.0")
    memories: List[ElementMemory] = Field(default_factory=list)


class PopupWatchdogConfig(BaseModel):
    """弹窗 Watchdog 配置"""

    enabled: bool = Field(default=True)
    strategy: str = Field(default="aggressive")
    custom_selectors: List[str] = Field(default_factory=list)
    whitelist_selectors: List[str] = Field(default_factory=list)
    scan_on_step: bool = Field(default=True)
    scan_on_navigation: bool = Field(default=True)
    scan_delay_ms: int = Field(default=500)
    z_index_threshold: int = Field(default=1000)
    overlay_min_area_ratio: float = Field(default=0.3)


class ElementMemoryConfig(BaseModel):
    """元素记忆配置"""

    enabled: bool = Field(default=True)
    storage_path: str = Field(default="./memory/elements.json")
    key_mode: str = Field(default="flat")
    match_mode: str = Field(default="exact")
    max_memories: int = Field(default=50000)  # 无过滤策略下几乎不设上限，全量保留经验
    auto_learn: bool = Field(default=True)
    min_retry_threshold: int = Field(default=2)
    # 命中即自动设值（确定性绕过 LLM 试错）
    auto_apply_enabled: bool = Field(default=True)
    # 日期范围窗口：查"今天往前 N 天 ~ 今天往前 1 天"（不含今天）
    # 例：days_back=10, include_today=False，今天 09-06 -> 08-26 ~ 09-05
    date_range_days_back: int = Field(default=10)
    date_range_include_today: bool = Field(default=False)


class AppConfig(BaseModel):
    """全局配置"""

    popup_watchdog: PopupWatchdogConfig = Field(default_factory=PopupWatchdogConfig)
    element_memory: ElementMemoryConfig = Field(default_factory=ElementMemoryConfig)
