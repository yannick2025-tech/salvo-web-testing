"""统一配置加载。

从 config.yaml 读取总配置：模型(llm)、应用(app)、元素记忆(element_memory)、
弹窗看门狗(popup_watchdog)。element_memory / popup_watchdog 与
browser_use_ext 的 AppConfig 同结构，runner 会把它传给 create_memory_agent。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    """单个模型的配置。"""

    api_key_env: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = Field(default=0.0)


class LLMConfig(BaseModel):
    """模型总配置：当前 provider + 各 provider 明细。"""

    provider: str = "deepseek"
    deepseek: ProviderConfig = Field(default_factory=ProviderConfig)
    qwen: ProviderConfig = Field(default_factory=ProviderConfig)

    def active(self) -> tuple[str, ProviderConfig]:
        """返回 (provider 名, 当前生效的 ProviderConfig)。"""
        name = self.provider.lower()
        cfg = getattr(self, name, None)
        if cfg is None:
            raise ValueError(f"未知 provider: {self.provider}，支持: deepseek / qwen")
        return name, cfg


class AppConfig(BaseModel):
    """应用级配置。"""

    login_url: str = ""


class Config(BaseModel):
    """总配置。"""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    app: AppConfig = Field(default_factory=AppConfig)
    element_memory: dict[str, Any] = Field(default_factory=dict)
    popup_watchdog: dict[str, Any] = Field(default_factory=dict)


def load_config(path: Optional[str] = None) -> Config:
    """从 YAML 加载总配置。

    Args:
        path: 配置文件路径，默认项目根目录 config.yaml（可用环境变量 CONFIG_PATH 覆盖）。

    Returns:
        Config 实例。
    """
    cfg_path = path or os.environ.get("CONFIG_PATH") or _default_path()
    p = Path(cfg_path)
    if not p.exists():
        raise FileNotFoundError(f"配置文件不存在: {p}")

    with open(p, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return Config.model_validate(data)


def _default_path() -> str:
    """默认配置路径：项目根目录 config.yaml。"""
    return str(Path(__file__).resolve().parent.parent / "config.yaml")
