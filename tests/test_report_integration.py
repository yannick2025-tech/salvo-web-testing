"""generate_report 集成测试：伪造 history + 用例，产出聚合 HTML + 截图目录。"""

import base64
from pathlib import Path
from types import SimpleNamespace

from app.report import generate_report
from app.report.models import RunResult


class _FakeAction:
    def __init__(self, name, params):
        self._name = name
        self._params = params

    def model_dump(self, exclude_unset=True):
        return {self._name: self._params}


class _FakeMO:
    def __init__(self, action, thinking="", next_goal="", evaluation=""):
        self.thinking = thinking
        self.next_goal = next_goal
        self.evaluation_previous_goal = evaluation
        self.action = action


class _FakeElement:
    def __init__(self, text=""):
        self.ax_name = text
        self.attributes = {}
        self.node_value = ""


class _FakeState:
    def __init__(self, url="", title="", interacted_text="", screenshot_b64=None):
        self.url = url
        self.title = title
        self.interacted_element = [_FakeElement(interacted_text)] if interacted_text else []
        self._screenshot = screenshot_b64

    def get_screenshot(self):
        return self._screenshot


class _FakeResult:
    def __init__(self, success=True, error=None):
        self.success = success
        self.error = error


class _FakeMeta:
    def __init__(self, duration):
        self._d = duration

    def duration_seconds(self):
        return self._d


class _FakeItem:
    def __init__(self, mo, state, result, meta=None):
        self.model_output = mo
        self.state = state
        self.result = result
        self.metadata = meta


class _FakeUsage:
    def model_dump(self):
        return {"total_tokens": 123, "total_prompt_tokens": 100}


class _FakeHistory:
    def __init__(self, items, success=True, final="ok"):
        self.history = items
        self.usage = _FakeUsage()
        self._success = success
        self._final = final

    def is_successful(self):
        return self._success

    def final_result(self):
        return self._final


def _item(action_name, params, interacted_text="", screenshot=True, success=True, thinking=""):
    b64 = base64.b64encode(b"fake-png").decode() if screenshot else None
    return _FakeItem(
        _FakeMO([_FakeAction(action_name, params)], thinking=thinking),
        _FakeState(
            url="https://example.com",
            title="后台首页",
            interacted_text=interacted_text,
            screenshot_b64=b64,
        ),
        [_FakeResult(success=success)],
        _FakeMeta(1.5),
    )


def _case(name="登录测试"):
    return SimpleNamespace(
        name=name,
        description="desc",
        steps=[
            SimpleNamespace(action="goto", target="登录页", params={}),
            SimpleNamespace(action="click", target="登录按钮", params={}),
        ],
    )


def test_generate_report_produces_html_and_screenshots(tmp_path):
    history = _FakeHistory(
        [
            _item("go_to_url", {"url": "https://example.com"}),
            _item("click_element", {"index": 12}, interacted_text="登录按钮"),
        ]
    )
    config = SimpleNamespace(output_dir=str(tmp_path), detail=False)
    results = [RunResult(platform_alias="manhattan", case=_case(), history=history)]

    report_dir = generate_report(results, config, model="qwen3.7-max")

    p = Path(report_dir)
    assert (p / "report.html").exists()
    assert (p / "screenshots" / "1-1-1-1.png").exists()
    assert (p / "screenshots" / "1-1-2-1.png").exists()
    assert (p / "token_usage.log").exists()

    content = (p / "report.html").read_text(encoding="utf-8")
    assert "Web UI 测试报告" in content
    assert "登录按钮" in content
    assert "manhattan" in content
    assert "qwen3.7-max" in content
    assert 'src="screenshots/1-1-2-1.png"' in content
    assert "通过" in content  # 用例成功徽章


def test_generate_report_detail_mode_contains_thinking(tmp_path):
    history = _FakeHistory([_item("go_to_url", {"url": "u"}, thinking="思考中")])
    config = SimpleNamespace(output_dir=str(tmp_path), detail=True)
    results = [RunResult(platform_alias="manhattan", case=_case(), history=history)]

    report_dir = generate_report(results, config)
    content = (Path(report_dir) / "report.html").read_text(encoding="utf-8")
    assert "思考中" in content  # 详细模式展示 thinking


def test_generate_report_aggregates_multiple_cases(tmp_path):
    """两个用例聚合到一份报告：元信息 total=2、按平台分块、两行用例。"""
    h1 = _FakeHistory(
        [_item("click_element", {"index": 1}, interacted_text="登录按钮")],
        final="用例1成功",
    )
    h2 = _FakeHistory(
        [_item("click_element", {"index": 2}, interacted_text="查询")],
        final="用例2失败",
        success=False,
    )
    config = SimpleNamespace(output_dir=str(tmp_path), detail=False)
    results = [
        RunResult(platform_alias="manhattan", case=_case("用例A"), history=h1),
        RunResult(platform_alias="manhattan", case=_case("用例B"), history=h2),
    ]

    report_dir = generate_report(results, config, report_name="套件")

    content = (Path(report_dir) / "report.html").read_text(encoding="utf-8")
    assert "用例A" in content
    assert "用例B" in content
    assert "总用例" in content
    assert "2" in content  # 总用例数
    assert content.count('class="case"') >= 2  # 两行用例
