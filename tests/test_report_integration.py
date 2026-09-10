"""generate_report 集成测试：伪造 history + 用例，产出 HTML + 截图目录。"""

import base64
from pathlib import Path
from types import SimpleNamespace

from app.report import generate_report


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

    report_dir = generate_report(history, _case(), config)

    p = Path(report_dir)
    assert (p / "report.html").exists()
    assert (p / "screenshots" / "1-1.png").exists()
    assert (p / "screenshots" / "2-1.png").exists()
    assert (p / "token_usage.log").exists()

    content = (p / "report.html").read_text(encoding="utf-8")
    assert "登录测试" in content
    assert "登录按钮" in content
    assert 'src="screenshots/2-1.png"' in content
    assert "通过" in content  # 整体成功徽章


def test_generate_report_detail_mode_contains_thinking(tmp_path):
    history = _FakeHistory([_item("go_to_url", {"url": "u"}, thinking="思考中")])
    config = SimpleNamespace(output_dir=str(tmp_path), detail=True)

    report_dir = generate_report(history, _case(), config)
    content = (Path(report_dir) / "report.html").read_text(encoding="utf-8")
    assert "思考中" in content  # 详细模式展示 thinking
