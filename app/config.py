"""统一配置加载。

从 config.yaml 读取总配置：模型(llm)、应用(app)、元素记忆(element_memory)、
弹窗看门狗(popup_watchdog)。element_memory / popup_watchdog 与
browser_use_ext 的 AppConfig 同结构，runner 会把它传给 create_memory_agent。
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Optional

import yaml
from pydantic import BaseModel, Field

# 匹配 ${VAR_NAME} 形式的环境变量占位符
_ENV_PATTERN = re.compile(r"\$\{(\w+)\}")


def expand_env_vars(obj: Any) -> Any:
    """递归地把字符串中的 ${VAR_NAME} 替换为环境变量值。

    未设置的环境变量保留原样（不替换），便于在 .env.example 里给出模板。
    用于 config.yaml 与 cases/*.yaml 中的敏感信息（域名、账号、密码）脱敏：
    文件里写占位符，真实值放本地 .env（已被 .gitignore 排除）。
    """
    if isinstance(obj, str):
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), m.group(0)), obj)
    if isinstance(obj, dict):
        return {k: expand_env_vars(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [expand_env_vars(v) for v in obj]
    return obj


class ProviderConfig(BaseModel):
    """单个模型的配置。"""

    api_key_env: str = ""
    base_url: str = ""
    model: str = ""
    temperature: float = Field(default=0.0)
    # 单次 LLM 输出 token 上限（qwen 走 OpenAI 兼容，默认 4096 在大 DOM 场景会截断）
    max_completion_tokens: int = Field(default=8192, ge=1024)


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


class Platform(BaseModel):
    """单个管理平台的注册信息。"""

    host: str = ""          # 域名（精确匹配，用于记忆分片路由）
    login_url: str = ""     # 该平台的登录 URL（用例 goto 步骤默认注入）


class RunnerConfig(BaseModel):
    """执行器参数：透传给 browser-use Agent。"""

    llm_timeout: int = Field(default=120, ge=30, description="单次 LLM 调用超时（秒）")
    step_timeout: int = Field(default=180, ge=30, description="单步整体超时（秒）")
    max_actions_per_step: int = Field(default=5, ge=1, le=20, description="LLM 每步最多输出 action 数")
    max_failures: int = Field(default=5, ge=1, description="连续失败次数上限，超过则停")
    # DOM 视口裁剪（方案B）：收紧 browser-use 视口阈值（默认 1000 → 200）
    viewport_threshold: Optional[int] = Field(default=200, ge=0, description="DOM 序列化视口阈值（像素），None=用 browser-use 默认 1000")
    # 工具精简（方案C1）：排除本项目用不到的工具
    tool_exclude: list[str] = Field(
        default_factory=lambda: [
            "search",
            "upload_file",
            "save_as_pdf",
            "write_file",
            "replace_file",
            "read_file",
            "find_text",
            "close",
        ],
        description="排除的工具名清单",
    )


class ProfilingConfig(BaseModel):
    """计量配置：量化 prompt 各部分 token 占比（纯观测，不影响执行）。"""

    enabled: bool = True


class ReportConfig(BaseModel):
    """HTML 测试报告生成配置。"""

    output_dir: str = Field(default="./reports", description="报告输出根目录")
    detail: bool = Field(default=False, description="详细模式（额外含 thinking/URL/token 等）")


class Config(BaseModel):
    """总配置。"""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    # 平台注册表：别名 -> Platform。别名同时作为记忆分片目录名与用例组目录名。
    platforms: dict[str, Platform] = Field(default_factory=dict)
    element_memory: dict[str, Any] = Field(default_factory=dict)
    popup_watchdog: dict[str, Any] = Field(default_factory=dict)
    runner: RunnerConfig = Field(default_factory=RunnerConfig)
    profiling: ProfilingConfig = Field(default_factory=ProfilingConfig)
    report: ReportConfig = Field(default_factory=ReportConfig)

    def resolve_platform(self, host: str) -> Optional[str]:
        """按 host 精确匹配平台，返回平台别名；未命中返回 None。"""
        for alias, platform in self.platforms.items():
            if platform.host and platform.host == host:
                return alias
        return None

    def platform(self, alias: str) -> Optional[Platform]:
        """按别名取平台。"""
        return self.platforms.get(alias)

    def platform_login_url(self, alias: str) -> str:
        """取指定平台的登录 URL；缺失时返回空串。"""
        p = self.platforms.get(alias)
        return p.login_url if p else ""


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
    # 敏感信息脱敏：配置文件里的 ${VAR} 占位符在此替换为环境变量值。
    data = expand_env_vars(data)
    return Config.model_validate(data)


def _default_path() -> str:
    """默认配置路径：项目根目录 config.yaml。"""
    return str(Path(__file__).resolve().parent.parent / "config.yaml")
