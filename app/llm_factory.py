"""模型统一加载（注册表模式）。

集中处理模型差异，用例/runner 中不得出现复用的 if 判断。
新增模型只需在 PROVIDER 注册表中加一项。

当前支持：
- deepseek：browser-use 内置 ChatDeepSeek。
- qwen：阿里千问，走 DashScope 的 OpenAI 兼容端点（复用 ChatOpenAI）。

KEY 从环境变量读取（.env 由 runner 加载）。
"""

from __future__ import annotations

import os
from typing import Any, Callable

from browser_use.llm import ChatDeepSeek, ChatOpenAI

from .config import Config, ProviderConfig

# 注册表：provider 名 -> 构造 client 的函数
_PROVIDERS: dict[str, Callable[[ProviderConfig], Any]] = {}


def _register(name: str):
    def decorator(fn: Callable[[ProviderConfig], Any]):
        _PROVIDERS[name] = fn
        return fn

    return decorator


def _api_key(env_name: str) -> str:
    key = os.environ.get(env_name, "")
    if not key:
        raise ValueError(f"缺少环境变量 {env_name}，请在 .env 中配置")
    return key


@_register("deepseek")
def _build_deepseek(cfg: ProviderConfig) -> Any:
    return ChatDeepSeek(
        api_key=_api_key(cfg.api_key_env),
        base_url=cfg.base_url,
        model=cfg.model,
        temperature=cfg.temperature,
    )


@_register("qwen")
def _build_qwen(cfg: ProviderConfig) -> Any:
    return ChatOpenAI(
        api_key=_api_key(cfg.api_key_env),
        base_url=cfg.base_url,
        model=cfg.model,
        temperature=cfg.temperature,
        max_completion_tokens=cfg.max_completion_tokens,
    )


def create_llm(config: Config) -> Any:
    """根据总配置的 llm.provider 构造 LLM 实例。"""
    name, active = config.llm.active()
    builder = _PROVIDERS.get(name)
    if builder is None:
        raise ValueError(f"未注册的 provider: {name}，支持: {', '.join(_PROVIDERS)}")
    return builder(active)


def supported_providers() -> list[str]:
    """返回支持的 provider 列表。"""
    return list(_PROVIDERS.keys())
