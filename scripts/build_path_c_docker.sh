#!/usr/bin/env bash
# 重建 matebookego_hyperos 的 super 镜像。
#
# 平台：Windows（Git Bash + Docker Desktop）或 Linux/macOS（Docker Engine）。
# 产物：out/super.raw.img.zst + out/SHA256SUMS + reports/super-layout.json
# 刷机：在平板的 USB Linux 里运行 ./flash.sh（见 README）。
#
# 设计要点：
#   * overlay.py 必须在 stage 之后运行（它依赖 stage 复制出的 work/framework-res.apk）。
#   * 宿主侧 Android build-tools 使用 bt36/ 里的 x86_64 二进制，因此容器固定 linux/amd64；
#     adapt 阶段的 secilc 在容器内 chroot 到 arm64 Android 根，走 Docker Desktop 的
#     qemu-aarch64 binfmt（已实测可用）。
set -euo pipefail

export MSYS_NO_PATHCONV=1
cd "$(dirname "$0")/.."
ROOT="$(pwd -W 2>/dev/null || pwd)"
IMAGE="${IMAGE:-pad9-port-tools:amd64}"
CONTAINER=pad9-port-build

cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
}
trap cleanup EXIT

die() { echo "错误：$*" >&2; exit 1; }

echo "===== 1/8 检查环境与输入 ====="
command -v docker >/dev/null || die "找不到 docker"
docker info >/dev/null 2>&1 || die "Docker 未启动或当前用户无权访问"
command -v python3 >/dev/null || die "找不到 python3"

required=(
  input/pad9/system.img
  input/pad9/system_ext.img
  input/pad9/product.img
  input/pad9/mi_ext.img
  input/pad9/mi_product.img
  input/crdroid-system.img
  input/crdroid-vendor.img
  input/super-metadata.bin
  input/crdroid-getprop.txt
  bt36/android-16/aapt2
  assets/overlay/AndroidManifest.xml
  overlay.keystore
)
for f in "${required[@]}"; do
  [ -e "$f" ] || die "缺少构建输入：$f"
done
echo "输入检查通过。"

echo "===== 2/8 清理上次构建残留 ====="
cleanup
docker run --rm -v "$ROOT:/work" alpine \
  sh -c 'rm -rf /work/out/* /work/work/* /work/reports/* && echo cleaned'

echo "===== 3/8 准备构建镜像 ====="
if docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "复用本地 $IMAGE"
else
  docker build --platform linux/amd64 -t "$IMAGE" .
fi

echo "===== 4/8 启动构建容器 ====="
docker run -d --name "$CONTAINER" --platform linux/amd64 --privileged \
  --mount "type=bind,source=$ROOT,target=/work" "$IMAGE" sleep infinity >/dev/null
docker exec "$CONTAINER" uname -m

echo "===== 5/8 stage：解包分区并复制 crDroid vendor ====="
docker exec "$CONTAINER" python3 scripts/build.py stage

echo "===== 6/8 overlay：编译并签名 RRO ====="
docker exec "$CONTAINER" bash -c '
  set -e
  rm -rf /opt/asdk
  mkdir -p /opt/asdk/build-tools/36.0.0
  cp -a /work/bt36/android-16/. /opt/asdk/build-tools/36.0.0/
  chmod -R +x /opt/asdk/build-tools/36.0.0
  export ANDROID_HOME=/opt/asdk
  python3 scripts/overlay.py'

echo "===== 7/8 adapt + 封装 super ====="
docker exec "$CONTAINER" python3 scripts/build.py adapt
docker exec "$CONTAINER" python3 scripts/pack_super.py --output out --report-dir reports
docker exec "$CONTAINER" img2simg out/super.raw.img out/super.img
docker exec "$CONTAINER" zstd -T4 -3 -f out/super.raw.img -o out/super.raw.img.zst
docker exec "$CONTAINER" sh -c 'cd out && sha256sum super.raw.img.zst > SHA256SUMS'

echo "===== 8/8 校验产物 ====="
python3 scripts/verify_artifact.py --artifact out
ls -la out/super.raw.img.zst out/SHA256SUMS reports/super-layout.json
cat out/SHA256SUMS
echo
echo "构建完成。下一步："
echo "  1) ./deploy.sh promote   # 把新镜像晋升为 artifact/ 下的部署产物"
echo "  2) 在平板 USB Linux 中运行 ./flash.sh --disk /dev/nvme0n1 --write"
