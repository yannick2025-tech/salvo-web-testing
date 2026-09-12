"""统一测试执行器（支持套件与批跑）。

用法：
    python -m app.runner cases/manhattan/query_orders.yaml          # 单个文件
    python -m app.runner cases/manhattan/                            # 目录（批跑所有 yaml）
    python -m app.runner cases/manhattan/ cases/other/a.yaml         # 多文件/多目录

一个 YAML 可以是：
- 套件（suite）：setup（公共前置，如登录）+ cases（多个用例），登录一次、复用会话依次执行。
- 单用例（旧格式）：顶层 steps，视为单用例套件。

流程：展开输入 → 对每个套件执行（setup 一次 + 各 case 复用 session）→ 收集结果 → 聚合一份报告。
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from .case_loader import load_suite
from .config import Config, load_config
from .llm_factory import create_llm
from .task_builder import build_steps_task

logger = logging.getLogger("app.runner")


def _browser_profile(keep_alive: bool = False) -> Any:
    """构造 browser-use 的 BrowserProfile（复用原 uat-login 的配置）。"""
    from browser_use.browser.profile import BrowserProfile

    return BrowserProfile(
        enable_default_extensions=False,
        ignore_default_args=[
            "--extensions-on-chrome-urls",
            "--disable-extensions-http-throttling",
            "--disable-default-apps",
        ],
        keep_alive=keep_alive,
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
    if len(parts) >= 2 and "cases" in parts:
        idx = list(parts).index("cases")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return None


def _expand_inputs(paths: list[str]) -> list[str]:
    """展开输入：目录 -> 其下所有 *.yaml；文件 -> 单个；去重排序。"""
    result: list[str] = []
    for p in paths:
        path = Path(p)
        if path.is_dir():
            result.extend(str(f) for f in sorted(path.glob("*.yaml")))
        elif path.is_file():
            result.append(str(path))
        else:
            logger.warning("忽略不存在的路径: %s", p)
    return sorted(set(result))


def _is_successful(history: Any) -> bool:
    fn = getattr(history, "is_successful", None)
    if callable(fn):
        try:
            return fn() is True
        except Exception:
            return False
    return False


async def _run_suite(
    suite_path: str, config: Config, platform_alias: str | None
) -> list[Any]:
    """执行一个套件：setup 一次 + 各 case 复用同一 session，返回 RunResult 列表。"""
    from .report.models import RunResult
    from browser_use_ext.integration import create_memory_agent

    llm = create_llm(config)
    platform = config.platform(platform_alias) if platform_alias else None
    suite = load_suite(
        suite_path,
        account=platform.account if platform else "",
        password=platform.password if platform else "",
    )
    login_url = config.platform_login_url(platform_alias) if platform_alias else ""
    logger.info(
        "套件: %s（setup=%d 步，%d 个用例，平台=%s）",
        suite.name,
        len(suite.setup),
        len(suite.cases),
        platform_alias or "-",
    )

    rc = config.runner
    session = None
    results: list[Any] = []

    # 组装执行单元：setup（若有）+ 各 case
    units: list[tuple[Any, Any]] = []
    if suite.setup:
        units.append((None, suite.setup))  # None 表示 setup
    for case in suite.cases:
        units.append((case, case.steps))

    try:
        setup_failed = False
        for case, steps in units:
            task = build_steps_task(steps, login_url)
            agent = create_memory_agent(
                task=task,
                llm=llm,
                config=_build_memory_config(config, platform_alias),
                use_vision=False,
                browser_profile=_browser_profile(keep_alive=True),
                browser_session=session,
                use_judge=False,
                llm_timeout=rc.llm_timeout,
                step_timeout=rc.step_timeout,
                max_actions_per_step=rc.max_actions_per_step,
                max_failures=rc.max_failures,
                viewport_threshold=rc.viewport_threshold,
                tool_exclude=rc.tool_exclude,
                profiling_enabled=config.profiling.enabled,
            )
            history = await agent.run()
            session = agent.browser_session  # 保存 session 供复用

            if case is None:  # setup（登录）
                _print_token_usage(history)
                if not _is_successful(history):
                    setup_failed = True
                    logger.warning("套件 setup(登录) 失败，跳过所有用例")
                    break
                continue

            # 业务用例
            print(f"\n===== 用例结果: {case.name} =====")
            print(history.final_result())
            _print_token_usage(history)
            results.append(
                RunResult(
                    platform_alias=platform_alias or "",
                    case=case,
                    history=history,
                )
            )

        # setup 失败：所有用例标记「未执行」
        if setup_failed:
            for case in suite.cases:
                results.append(
                    RunResult(
                        platform_alias=platform_alias or "",
                        case=case,
                        history=None,
                        note="登录失败",
                    )
                )
    finally:
        if session is not None:
            try:
                await session.kill()
            except Exception:  # noqa: BLE001 —— 收尾失败不影响结果
                pass

    return results


async def _run(
    paths: list[str],
    config: Config,
    report_enabled: bool,
    platform_override: str | None,
) -> None:
    suite_paths = _expand_inputs(paths)
    if not suite_paths:
        logger.error("没有可执行的用例文件")
        return

    all_results: list[Any] = []
    for suite_path in suite_paths:
        platform_alias = platform_override or _infer_platform(suite_path)
        if platform_alias and not config.platform(platform_alias):
            logger.warning(
                "平台 %r 未在 config.yaml 的 platforms 中注册，登录 URL 将为空",
                platform_alias,
            )
        try:
            all_results.extend(await _run_suite(suite_path, config, platform_alias))
        except Exception as e:  # noqa: BLE001 —— 单个套件失败不影响其余
            logger.error("套件 %s 执行失败: %s", suite_path, e)

    if report_enabled and all_results:
        report_name = Path(suite_paths[0]).stem if len(suite_paths) == 1 else "batch"
        _generate_report(all_results, config, report_name)


def _generate_report(results: list[Any], config: Config, report_name: str) -> None:
    """聚合生成 HTML 测试报告（异常不影响主流程）。"""
    try:
        from .report import generate_report

        _, provider = config.llm.active()
        model = provider.model
        report_dir = generate_report(
            results,
            config.report,
            model=model,
            report_name=report_name,
        )
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
    parser.add_argument(
        "case",
        nargs="+",
        help="测试用例 YAML 路径或目录（可多个，目录批跑其下所有 yaml）",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="总配置文件路径（默认项目根目录 config.yaml）",
    )
    parser.add_argument(
        "--platform",
        default=None,
        help="平台别名（覆盖所有用例的平台推断）",
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
    asyncio.run(_run(args.case, config, args.report, args.platform))
    return 0


if __name__ == "__main__":
    sys.exit(main())
