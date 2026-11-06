#!/system/bin/sh
# gaokun3 GPU 频率调度 —— post-fs-data 阶段早期应用。
#
# 在 SurfaceFlinger 启动前就把 GPU min_freq 设好，确保开机首帧就流畅。
# 仅在 fixed 模式下应用 FIXED_FREQ；dynamic 模式由 service.sh 起守护进程
# 管理（post-fs-data 阶段屏幕状态不稳定，不宜轮询）。
#
# ⚠️ PATH 钉 /system/bin（与 thermal-guard.sh 同理：避免 /vendor/bin 优先
#    导致 toybox_vendor 权限问题）。
PATH=/system/bin:/system/xbin
export PATH

GPU=/sys/class/devfreq/3d00000.gpu
MODDIR=$(cd "$(dirname "$0")" && pwd)

# 读取配置：优先持久副本，回退模块内默认
CONF=/data/adb/gaokun3_gpu_freq.conf
[ -f "$CONF" ] || CONF=$MODDIR/config.conf

# 逐行解析 KEY=VALUE（跳过注释和空行）
getconf_val() {
    grep "^$1=" "$CONF" 2>/dev/null | head -1 | cut -d= -f2-
}

MODE=$(getconf_val MODE)
FIXED_FREQ=$(getconf_val FIXED_FREQ)

# GPU 节点不存在则跳过（非 gaokun3 设备）
[ -d "$GPU" ] || exit 0

# fixed 模式：早期锁定。dynamic 模式：先设成 SCREEN_ON_FREQ 作为安全初始值，
# 等 service.sh 起守护进程接管。
if [ "$MODE" = "dynamic" ]; then
    SCREEN_ON_FREQ=$(getconf_val SCREEN_ON_FREQ)
    [ -n "$SCREEN_ON_FREQ" ] && echo "$SCREEN_ON_FREQ" > "$GPU/min_freq" 2>/dev/null
else
    # fixed 或未识别模式
    [ -n "$FIXED_FREQ" ] && echo "$FIXED_FREQ" > "$GPU/min_freq" 2>/dev/null
fi

exit 0
