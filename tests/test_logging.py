"""运行日志双路输出（console + 文件）的单元测试。"""

from __future__ import annotations

import logging

from app.runner import _setup_logging


def test_setup_logging_writes_file(tmp_path):
    """_setup_logging 应创建日志文件，并把日志写入文件（console 输出保持不变）。

    回归点：FileHandler 是 StreamHandler 的子类，判断时需用 type 精确区分，
    避免把文件 handler 误当成 console handler。
    """
    log_file = _setup_logging(str(tmp_path), "INFO")

    try:
        assert log_file.exists(), "应创建日志文件"

        root = logging.getLogger()
        assert any(type(h) is logging.FileHandler for h in root.handlers), "缺 FileHandler"

        logging.getLogger("test.logging").info("dual-output-ok")
        assert "dual-output-ok" in log_file.read_text(encoding="utf-8"), "日志应写入文件"
    finally:
        # 清理测试加入的 FileHandler，避免污染其他测试的 root logger
        root = logging.getLogger()
        for h in list(root.handlers):
            if type(h) is logging.FileHandler:
                h.close()
                root.removeHandler(h)
