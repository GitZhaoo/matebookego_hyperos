#!/usr/bin/env bash
# 在平板的 USB Linux（Fedora / Ubuntu）里刷入 HyperOS super。
#
#   sudo ./flash.sh --list
#   sudo ./flash.sh --disk /dev/nvme0n1            # 只显示计划
#   sudo ./flash.sh --disk /dev/nvme0n1 --write    # 真正写入并清空 userdata/metadata
#
# 只写 super，保留 boot / EFI / vendor 分区；刷完手动重启，选内置盘的 Android A。
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$(pwd)"

if [ "$(uname -s)" != "Linux" ]; then
  echo "flash.sh 必须在平板的 USB Linux 中运行（Windows 只能构建，不能刷写）。" >&2
  exit 1
fi
if grep -qi microsoft /proc/version 2>/dev/null; then
  echo "检测到 WSL：请不要从 WSL 刷写内置磁盘，改用平板的 Fedora/Ubuntu USB 系统。" >&2
  exit 1
fi

if [ "$(id -u)" -ne 0 ]; then
  exec sudo -- bash "$ROOT/flash.sh" "$@"
fi

[ -f artifact/super.raw.img.zst ] || { echo "缺少 artifact/super.raw.img.zst" >&2; exit 1; }
[ -f artifact/SHA256SUMS ] || { echo "缺少 artifact/SHA256SUMS" >&2; exit 1; }
command -v python3 >/dev/null || { echo "缺少 python3" >&2; exit 1; }
command -v zstd >/dev/null || { echo "缺少 zstd" >&2; exit 1; }

exec python3 scripts/flash.py \
  --image artifact/super.raw.img.zst \
  --checksums artifact/SHA256SUMS \
  "$@"
