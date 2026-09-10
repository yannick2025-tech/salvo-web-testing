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


def _build_memory_config(config: Config, platform_alias: str | None) -> Any:
    """把总配置里的 element_memory/popup_watchdog 段构造成 browser_use_ext 的 AppConfig。"""
    from browser_use_ext.memory.models import AppConfig

    element_memory = dict(config.element_memory or {})
    # 把平台上下文注入记忆配置，供分片路由（host -> 平台目录）使用。
    if platform_alias:
        platform = config.platform(platform_alias)
        if platform:
            element_memory["platform_alias"] = platform_alias
            element_memory["platform_host"] = platform.host

    return AppConfig.model_validate(
        {
            "element_memory": element_memory,
            "popup_watchdog": config.popup_watchdog or {},
        }
    )


def _infer_platform(case_path: str) -> str | None:
    """从用例路径推断平台别名：cases/<platform>/<case>.yaml -> <platform>。

    仅当路径形如 cases/<alias>/... 时返回别名，否则返回 None。
    """
    parts = Path(case_path).parts
    if len(parts) >= 2 and parts[-2] != "cases" and "cases" in parts:
        idx = list(parts).index("cases")
        if idx + 1 < len(parts) - 1:
            return parts[idx + 1]
    return None


async def _run(
    case_path: str, config: Config, platform_alias: str | None, report_enabled: bool
) -> None:
    from browser_use_ext.integration import create_memory_agent

    # 1. 建模型
    llm = create_llm(config)

    # 2. 加载用例并转 task
    case = load_case(case_path)
    login_url = config.platform_login_url(platform_alias) if platform_alias else ""
    task = build_task(case, login_url)
    logger.info("用例: %s (%d 步, 平台=%s)", case.name, len(case.steps), platform_alias or "-")

    # 3. 装配 agent（runner 段配置透传给 browser-use Agent）
    rc = config.runner
    agent = create_memory_agent(
        task=task,
        llm=llm,
        config=_build_memory_config(config, platform_alias),
        use_vision=False,
        browser_profile=_browser_profile(),
        use_judge=False,
        llm_timeout=rc.llm_timeout,
        step_timeout=rc.step_timeout,
        max_actions_per_step=rc.max_actions_per_step,
        max_failures=rc.max_failures,
        viewport_threshold=rc.viewport_threshold,
        tool_exclude=rc.tool_exclude,
        profiling_enabled=config.profiling.enabled,
    )

    # 4. 执行
    history = await agent.run()
    print("\n===== Agent Result =====")
    print(history.final_result())

    # 5. 打印 token 用量（用于对比"加记忆前/后"的调用 token 差异）
    _print_token_usage(history)

    # 6. 生成 HTML 报告（按开关；报告失败不影响主流程）
    if report_enabled:
        _generate_report(history, case, config)


def _generate_report(history: Any, case: Any, config: Config) -> None:
    """生成 HTML 测试报告（异常/中断也尽力生成，失败不影响主流程）。"""
    try:
        from .report import generate_report

        report_dir = generate_report(history, case, config.report)
        logger.info("测试报告已生成: %s/report.html", report_dir)
    except Exception as e:  # noqa: BLE001 —— 报告失败不影响主流程
        logger.warning("测试报告生成失败(不影响主流程): %s", e)


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
    parser.add_argument(
        "--platform",
        default=None,
        help="平台别名（缺省时从用例路径 cases/<platform>/... 推断）",
    )
    parser.add_argument(
        "--report",
        dest="report",
        action="store_true",
        default=True,
        help="生成 HTML 测试报告（默认开启）",
    )
    parser.add_argument(
        "--no-report",
        dest="report",
        action="store_false",
        help="关闭 HTML 测试报告生成",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    config = load_config(args.config)

    # 平台解析：显式 --platform 优先，否则从用例路径推断
    platform_alias = args.platform or _infer_platform(args.case)
    if platform_alias and not config.platform(platform_alias):
        logger.warning(
            "平台 %r 未在 config.yaml 的 platforms 中注册，登录 URL 将为空",
            platform_alias,
        )

    asyncio.run(_run(args.case, config, platform_alias, args.report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
