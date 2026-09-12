"""平台级登录凭据注入单元测试。"""

import yaml

from app.case_loader import load_suite
from app.config import expand_env_vars


def _write_suite(path):
    """写一个用 ${ACCOUNT}/${PASSWORD} 占位符的套件。"""
    data = {
        "name": "冒烟",
        "setup": [
            {"action": "input", "target": "请输入您的账号", "params": {"value": "${ACCOUNT}"}},
            {"action": "input", "target": "请输入您的密码", "params": {"value": "${PASSWORD}"}},
        ],
        "cases": [
            {"name": "用例A", "steps": [{"action": "click", "target": "查询"}]},
        ],
    }
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return str(path)


def test_expand_env_vars_extra_priority():
    """extra 映射优先于环境变量。"""
    assert expand_env_vars("${ACCOUNT}", {"ACCOUNT": "manhattan账号"}) == "manhattan账号"


def test_expand_env_vars_keeps_unknown():
    """extra 与环境都无此变量时保留原占位符。"""
    assert expand_env_vars("${NOT_EXIST}", {"ACCOUNT": "x"}) == "${NOT_EXIST}"


def test_load_suite_injects_credentials(tmp_path):
    f = tmp_path / "suite.yaml"
    path = _write_suite(f)

    suite = load_suite(path, account="manhattan账号", password="manhattan密码")
    assert suite.setup[0].params["value"] == "manhattan账号"
    assert suite.setup[1].params["value"] == "manhattan密码"


def test_load_suite_keeps_placeholder_when_no_credentials(tmp_path):
    f = tmp_path / "suite.yaml"
    path = _write_suite(f)

    suite = load_suite(path)
    assert suite.setup[0].params["value"] == "${ACCOUNT}"
    assert suite.setup[1].params["value"] == "${PASSWORD}"


def test_load_suite_platform_isolation(tmp_path):
    """不同平台账号不同，各自加载结果互不串。"""
    f = tmp_path / "suite.yaml"
    path = _write_suite(f)

    s_manhattan = load_suite(path, account="manhattan账号", password="manhattan密码")
    s_owner = load_suite(path, account="owner账号", password="owner密码")

    assert s_manhattan.setup[0].params["value"] == "manhattan账号"
    assert s_owner.setup[0].params["value"] == "owner账号"
    # 密码也不串
    assert s_manhattan.setup[1].params["value"] == "manhattan密码"
    assert s_owner.setup[1].params["value"] == "owner密码"
