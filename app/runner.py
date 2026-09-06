"""统一测试执行器。

用法：
    python -m app.runner cases/login_and_query.yaml

流程：加载 .env → 读 config.yaml → 建模型 → 加载用例 → 转 task → 装配 agent → 执行。
不动态生成 py 文件。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .case_loader import load_case
from .config import Config, load_config
from .llm_factory import create_llm
from .task_builder import build_task

logger = logging.getLogger("app.runner")


def _browser_profile() -> Any:
    """构造 browser-use 的 BrowserProfile（复用原 uat-login 的配置）。"""
    from browser_use.browser.profile import BrowserProfile

    return BrowserProfile(
        enable_default_extensions=False,
        ignore_default_args=[
            "--extensions-on-chrome-urls",
            "--disable-extensions-http-throttling",
            "--disable-default-apps",
        ],
    )


def _build_memory_config(config: Config) -> Any:
    """把总配置里的 element_memory/popup_watchdog 段构造成 browser_use_ext 的 AppConfig。"""
    from browser_use_ext.memory.models import AppConfig

    return AppConfig.model_validate(
        {
            "element_memory": config.element_memory or {},
            "popup_watchdog": config.popup_watchdog or {},
        }
    )


async def _run(case_path: str, config: Config) -> None:
    from browser_use_ext.integration import create_memory_agent

    # 1. 建模型
    llm = create_llm(config)

    # 2. 加载用例并转 task
    case = load_case(case_path)
    task = build_task(case, config.app.login_url)
    logger.info("用例: %s (%d 步)", case.name, len(case.steps))

    # 3. 装配 agent
    agent = create_memory_agent(
        task=task,
        llm=llm,
        config=_build_memory_config(config),
        use_vision=False,
        browser_profile=_browser_profile(),
        use_judge=False,
    )

    # 4. 执行
    history = await agent.run()
    print("\n===== Agent Result =====")
    print(history.final_result())

    # 5. 打印 token 用量（用于对比"加记忆前/后"的调用 token 差异）
    _print_token_usage(history)


def _print_token_usage(history: Any) -> None:
    """打印本次运行的 token 用量统计（不涉及费用）。"""
    usage = getattr(history, "usage", None)
    if usage is None:
        print("\n===== Token Usage =====")
        print("(无 token 用量数据)")
        return

    # usage 可能是 UsageSummary 对象或 dict，统一转 dict 输出
    data = usage.model_dump() if hasattr(usage, "model_dump") else usage
    if not isinstance(data, dict):
        data = vars(usage) if hasattr(usage, "__dict__") else {}

    print("\n===== Token Usage =====")
    print(f"  total_prompt_tokens   = {data.get('total_prompt_tokens', 0)}")
    print(f"  total_completion_tokens = {data.get('total_completion_tokens', 0)}")
    print(f"  total_tokens          = {data.get('total_tokens', 0)}")
    print(f"  total_prompt_cached   = {data.get('total_prompt_cached_tokens', 0)}")
    print(f"  entry_count           = {data.get('entry_count', 0)}")

    by_model = data.get("by_model") or {}
    if isinstance(by_model, dict) and by_model:
        print("  ---- by model ----")
        for model, stats in by_model.items():
            s = stats.model_dump() if hasattr(stats, "model_dump") else stats
            print(
                f"    {model}: prompt={s.get('prompt_tokens', 0)} "
                f"completion={s.get('completion_tokens', 0)} "
                f"total={s.get('total_tokens', 0)} "
                f"invocations={s.get('invocations', 0)}"
            )


def main(argv: list[str] | None = None) -> int:
    load_dotenv()  # 加载 .env 中的 API KEY

    parser = argparse.ArgumentParser(description="统一 Web 测试执行器")
    parser.add_argument("case", help="测试用例 YAML 路径")
    parser.add_argument(
        "--config",
        default=None,
        help="总配置文件路径（默认项目根目录 config.yaml）",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    config = load_config(args.config)
    asyncio.run(_run(args.case, config))
    return 0


if __name__ == "__main__":
    sys.exit(main())
