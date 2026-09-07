"""PromptUsageProfiler 单元测试。"""

from browser_use_ext.prompt_profiler import (
    PromptUsageProfiler,
    _text_len,
    est_tokens,
    extract_block,
    extract_dom_body,
)


def test_extract_block_basic():
    text = "<user_request>\nhello\n</user_request>"
    assert extract_block(text, "user_request") == "hello"


def test_extract_block_missing_returns_empty():
    assert extract_block("<user_request>x</user_request>", "agent_history") == ""


def test_extract_dom_body_strips_page_stats():
    text = (
        "<browser_state>\n"
        "<page_stats>10 links</page_stats>\n"
        "Interactive elements:\n"
        "[1]<button>查询</button>\n"
        "</browser_state>"
    )
    body = extract_dom_body(text)
    assert "[1]<button>" in body
    assert "page_stats" not in body


def test_extract_dom_body_handles_truncated_suffix():
    text = (
        "<browser_state>\n"
        "Interactive elements (truncated to 40000 characters):\n"
        "[1]<div />\n"
        "</browser_state>"
    )
    assert "[1]<div />" in extract_dom_body(text)


def test_est_tokens():
    assert est_tokens(400) == 100
    assert est_tokens(0) == 0
    assert est_tokens(7) == 1


def test_text_len_str_and_list():
    assert _text_len("abcd") == 4
    assert _text_len([{"text": "ab"}, {"text": "cde"}]) == 5
    assert _text_len(None) == 0


def test_record_state_splits_parts():
    profiler = PromptUsageProfiler()

    class FakeMM:
        last_state_message_text = (
            "<user_request>\n任务\n</user_request>\n\n"
            "<agent_history>\n历史内容\n</agent_history>\n\n"
            "<agent_state>\n状态\n</agent_state>\n"
            "<browser_state>\nInteractive elements:\nDOM主体\n</browser_state>\n"
        )

    profiler._record_state(FakeMM())

    assert len(profiler.steps) == 1
    s = profiler.steps[0]
    assert s["task+state"] > 0
    assert s["history"] > 0
    assert s["browser_state(DOM)"] > 0
    assert s["context"] == 0
    assert s["_dom_body"] > 0


def test_record_state_skips_non_text():
    profiler = PromptUsageProfiler()

    class FakeMM:
        last_state_message_text = None

    profiler._record_state(FakeMM())
    assert len(profiler.steps) == 1
    assert profiler.steps[0]["browser_state(DOM)"] == 0


def test_report_outputs_summary():
    profiler = PromptUsageProfiler()
    profiler.system_chars = 4000
    profiler.tools_chars = 2000
    profiler.steps = [
        {
            "system": 0,
            "tools": 0,
            "task+state": 100,
            "history": 50,
            "browser_state(DOM)": 800,
            "context": 10,
            "_dom_body": 700,
        }
    ]
    report = profiler.report()
    assert "Prompt Usage Profile" in report
    assert "system" in report
    assert "browser_state(DOM)" in report
    assert "TOTAL" in report


def test_report_empty_returns_placeholder():
    assert "无计量数据" in PromptUsageProfiler().report()


# ---- attach 端到端 mock 测试（不依赖真实 LLM / 浏览器） ----


class _FakeContextMessage:
    def __init__(self, content):
        self.content = content


class _FakeActionModel:
    def model_json_schema(self):
        return {"type": "object", "properties": {"action": {"type": "string"}}}


class _FakeSystemMessage:
    content = "system prompt"


class _FakeHistory:
    def __init__(self):
        self.system_message = _FakeSystemMessage()
        self.context_messages = []


class _FakeState:
    def __init__(self):
        self.history = _FakeHistory()


_STATE_TEXT = (
    "<user_request>\n任务\n</user_request>\n\n"
    "<agent_history>\n历史\n</agent_history>\n\n"
    "<agent_state>\n状态\n</agent_state>\n"
    "<browser_state>\nInteractive elements:\nDOM\n</browser_state>\n"
)


class _FakeMessageManager:
    def __init__(self):
        self.state = _FakeState()
        self.last_state_message_text = ""

    def create_state_messages(self, *args, **kwargs):
        self.last_state_message_text = _STATE_TEXT

    def get_messages(self):
        return []


class _FakeAgent:
    def __init__(self):
        self._message_manager = _FakeMessageManager()
        self.ActionModel = _FakeActionModel()


def test_attach_patches_and_records_end_to_end():
    profiler = PromptUsageProfiler()
    agent = _FakeAgent()
    mm = agent._message_manager

    profiler.attach(agent)

    # 固定开销已测
    assert profiler.system_chars > 0
    assert profiler.tools_chars > 0

    # 模拟每步：create_state_messages → _record_state
    mm.create_state_messages()
    assert len(profiler.steps) == 1
    assert profiler.steps[0]["history"] > 0
    assert profiler.steps[0]["browser_state(DOM)"] > 0
    assert profiler.steps[0]["_dom_body"] > 0

    # 模拟 context 注入后 get_messages → _record_context
    mm.state.history.context_messages.append(_FakeContextMessage("记忆提示"))
    mm.get_messages()
    assert profiler.steps[0]["context"] > 0

    # 汇总报告包含六部分
    report = profiler.report()
    assert "Prompt Usage Profile" in report
    assert "TOTAL" in report


def test_attach_skips_when_no_message_manager():
    profiler = PromptUsageProfiler()

    class NoMMAgent:
        pass

    profiler.attach(NoMMAgent())  # 不应抛异常
    assert profiler.steps == []
