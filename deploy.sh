#!/usr/bin/env bash
# matebookego_hyperos 一键入口。
#
#   ./deploy.sh build          从 input/ 重新构建 super，并晋升到 artifact/
#   ./deploy.sh promote        只把 out/ 里已验证的构建结果晋升到 artifact/
#   ./deploy.sh verify         校验 artifact/ 镜像、分区布局和关键输入
#   ./deploy.sh modules        打包 artifact/modules/*.zip
#   ./deploy.sh flash ...      转到 ./flash.sh（必须在平板 USB Linux 中运行）
set -euo pipefail
cd "$(dirname "$0")"

usage() {
  sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
}

promote() {
  [ -f out/super.raw.img.zst ] || { echo "out/super.raw.img.zst 不存在，先运行 ./deploy.sh build" >&2; exit 1; }
  [ -f out/SHA256SUMS ] || { echo "out/SHA256SUMS 不存在" >&2; exit 1; }
  python3 scripts/verify_artifact.py --artifact out
  mkdir -p artifact
  mv -f out/super.raw.img.zst artifact/super.raw.img.zst
  mv -f out/SHA256SUMS artifact/SHA256SUMS
  python3 scripts/pack_modules.py
  python3 scripts/verify_artifact.py
  echo "已晋升到 artifact/。"
}

cmd="${1:-}"
case "$cmd" in
  build)
    bash scripts/build_path_c_docker.sh
    promote
    ;;
  promote)
    promote
    ;;
  verify)
    python3 scripts/verify_artifact.py --check-inputs
    ;;
  modules)
    python3 scripts/pack_modules.py
    ;;
  flash)
    shift
    exec bash flash.sh "$@"
    ;;
  *)
    usage
    exit 1
    ;;
esac
