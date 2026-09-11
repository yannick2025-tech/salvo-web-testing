"""套件加载与批跑输入展开单元测试。"""

import yaml

import pytest

from app.case_loader import load_suite
from app.runner import _expand_inputs


def _write(path, data):
    path.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def test_load_suite_with_setup_and_cases(tmp_path):
    f = tmp_path / "suite.yaml"
    _write(
        f,
        {
            "name": "冒烟测试",
            "setup": [{"action": "goto", "target": "登录页"}],
            "cases": [
                {"name": "用例A", "steps": [{"action": "click", "target": "查询"}]},
                {"name": "用例B", "steps": [{"action": "click", "target": "导出"}]},
            ],
        },
    )
    suite = load_suite(str(f))
    assert suite.name == "冒烟测试"
    assert len(suite.setup) == 1
    assert len(suite.cases) == 2
    assert suite.cases[0].name == "用例A"


def test_load_suite_backward_compat_single_case(tmp_path):
    f = tmp_path / "case.yaml"
    _write(f, {"name": "单用例", "steps": [{"action": "goto", "target": "登录页"}]})
    suite = load_suite(str(f))
    assert len(suite.setup) == 0
    assert len(suite.cases) == 1
    assert suite.cases[0].name == "单用例"


def test_load_suite_rejects_unknown_action(tmp_path):
    f = tmp_path / "bad.yaml"
    _write(
        f,
        {
            "name": "x",
            "cases": [{"name": "c", "steps": [{"action": "bad_action", "target": "x"}]}],
        },
    )
    with pytest.raises(ValueError):
        load_suite(str(f))


def test_expand_inputs_dir_and_files(tmp_path):
    d = tmp_path / "cases" / "manhattan"
    d.mkdir(parents=True)
    (d / "a.yaml").write_text("a: 1", encoding="utf-8")
    (d / "b.yaml").write_text("b: 1", encoding="utf-8")
    (d / "c.txt").write_text("ignore", encoding="utf-8")
    single = tmp_path / "other.yaml"
    single.write_text("x: 1", encoding="utf-8")

    paths = _expand_inputs([str(d), str(single), str(single)])  # 含去重
    assert len(paths) == 3
    assert str(d / "a.yaml") in paths
    assert str(d / "b.yaml") in paths
    assert str(single) in paths
    assert str(d / "c.txt") not in paths  # 非 yaml 被忽略
