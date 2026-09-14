# py-web-testing Makefile
# 依赖统一走 uv（`uv run`），不再手写 pip/requirements。

# ---------- 清理脚本：按操作系统选择 ----------
ifeq ($(OS),Windows_NT)
CLEANUP := scripts/cleanup.bat
else
CLEANUP := ./scripts/cleanup.sh
endif

# ---------- 变量 ----------
RUNNER    := uv run python -m app.runner
PYTEST    := uv run pytest

# 单个用例运行时的默认目标
DEFAULT_CASE := cases/manhattan/smoke.yaml
CASE ?= $(DEFAULT_CASE)

# 清理保留天数（默认 3）
DAYS ?= 3

.PHONY: help test run run-all clean

.DEFAULT_GOAL := help

help:
	@echo "py-web-testing 任务说明"
	@echo ""
	@echo "用法: make <target> [变量=值]"
	@echo ""
	@echo "目标:"
	@echo "  test                  运行所有单元测试 (uv run pytest)"
	@echo "  run [CASE=<路径>]     运行单个用例（默认: $(DEFAULT_CASE)）"
	@echo "  run-all               批量运行 cases/ 下所有平台用例"
	@echo "  clean [DAYS=3]        清理 logs/reports，保留最近 DAYS 天"
	@echo ""
	@echo "示例:"
	@echo "  make test"
	@echo "  make run"
	@echo "  make run CASE=cases/franchisee/smoke.yaml"
	@echo "  make run-all"
	@echo "  make clean"
	@echo "  make clean DAYS=7"

test:
	$(PYTEST)

run:
	$(RUNNER) $(CASE)

run-all:
	$(RUNNER) $(wildcard cases/*/*.yaml)

clean:
	$(CLEANUP) $(DAYS)
