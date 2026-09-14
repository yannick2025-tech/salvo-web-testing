#!/usr/bin/env bash
#
# 清理 logs 日志与 reports 报告，只保留最近 N 天（默认 3 天）。
#
# 用法：
#   ./cleanup.sh          # 保留最近 3 天
#   ./cleanup.sh 7        # 保留最近 7 天
#
# 说明：
#   - 按「修改时间（mtime）」判断，超过 N 天的删除。
#   - logs/ 下删除 *.log（含 console.log、runner_*.log）。
#   - reports/batch/ 下删除超时的报告目录（时间戳目录）。
#   - reports/ 顶层其它报告目录（如 smoke、中文名目录等旧格式）同样按 mtime 清理。
#
set -euo pipefail

DAYS="${1:-3}"

# 脚本位于 scripts/ 目录，项目根目录为其上一级。
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

echo "==> 清理策略：保留最近 ${DAYS} 天，删除更早的日志与报告"
echo "==> 项目根目录：${ROOT}"

# 1) 清理 logs/ 下超过 N 天的 .log 文件
LOG_DIR="$ROOT/logs"
if [ -d "$LOG_DIR" ]; then
    echo "==> 清理日志: ${LOG_DIR}"
    find "$LOG_DIR" -maxdepth 1 -type f -name '*.log' -mtime +"$DAYS" -print -delete
fi

# 2) 清理 reports/batch/ 下超过 N 天的报告目录（时间戳目录）
BATCH_DIR="$ROOT/reports/batch"
if [ -d "$BATCH_DIR" ]; then
    echo "==> 清理批量报告: ${BATCH_DIR}"
    find "$BATCH_DIR" -maxdepth 1 -mindepth 1 -type d -mtime +"$DAYS" -print -exec rm -rf {} +
fi

# 3) 清理 reports/ 顶层其它报告目录（排除 batch 本身，避免误删整个 batch 容器）
REPORT_DIR="$ROOT/reports"
if [ -d "$REPORT_DIR" ]; then
    echo "==> 清理其它报告目录: ${REPORT_DIR}"
    find "$REPORT_DIR" -maxdepth 1 -mindepth 1 -type d ! -name 'batch' -mtime +"$DAYS" -print -exec rm -rf {} +
fi

echo "==> 完成"
