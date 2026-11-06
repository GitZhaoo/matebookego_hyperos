#!/system/bin/sh
# gaokun3 GPU 频率调度 —— apply.sh
#
# 运行时重新读取配置并立即生效（无需重启）。
# 用法：
#   adb shell su -c 'sh /data/adb/modules/gaokun3_gpu_freq/apply.sh'
#
# 行为：
#   - 先杀掉旧的 dynamic 守护进程
#   - fixed 模式：直接写 min_freq
#   - dynamic 模式：重新起守护进程
#
# 也支持把当前配置导出到持久副本 /data/adb/gaokun3_gpu_freq.conf，
# 这样模块更新后配置不丢失：
#   adb shell su -c 'sh .../apply.sh save'
#   adb shell su -c 'sh .../apply.sh reset'   # 删除持久副本，回退模块默认

PATH=/system/bin:/system/xbin
export PATH

GPU=/sys/class/devfreq/3d00000.gpu
MODDIR=$(cd "$(dirname "$0")" && pwd)
PERSIST_CONF=/data/adb/gaokun3_gpu_freq.conf
PIDFILE=/data/adb/gaokun3_gpu_freq.pid

ACTION="${1:-apply}"

# ── save / reset 子命令 ───────────────────────────────────────────
case "$ACTION" in
    save)
        cp "$MODDIR/config.conf" "$PERSIST_CONF"
        echo "已保存当前配置到 $PERSIST_CONF（模块更新后不丢失）"
        exit 0
        ;;
    reset)
        rm -f "$PERSIST_CONF"
        echo "已删除持久配置，回退模块默认值。执行 apply 生效。"
        exit 0
        ;;
esac

# ── apply（默认） ─────────────────────────────────────────────────
# 直接调用 service.sh 即可（它会杀旧进程 + 按新配置执行）。
# ⚠️ 用 setsid + 重定向脱离当前 stdout/stderr：service.sh 在 dynamic 模式下会
#    后台起守护进程，若不脱离 pipe，ksu.exec 会因 pipe 不关闭而永久挂起。
setsid sh "$MODDIR/service.sh" >/dev/null 2>&1

# 给 service.sh 一点时间完成（杀旧进程 + 起新守护进程）
sleep 1
echo "=== GPU 频率调度当前状态 ==="
echo "min_freq : $(cat "$GPU/min_freq" 2>/dev/null)"
echo "max_freq : $(cat "$GPU/max_freq" 2>/dev/null)"
echo "cur_freq : $(cat "$GPU/cur_freq" 2>/dev/null)"
echo "governor : $(cat "$GPU/governor" 2>/dev/null)"
if [ -f "$PIDFILE" ]; then
    pid=$(cat "$PIDFILE" 2>/dev/null)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        echo "守护进程 : 运行中 (pid=$pid, dynamic 模式)"
    else
        echo "守护进程 : 未运行 (PID 文件残留，已清理)"
        rm -f "$PIDFILE"
    fi
else
    echo "守护进程 : 未运行 (fixed 模式)"
fi

CONF="$PERSIST_CONF"
[ -f "$CONF" ] || CONF="$MODDIR/config.conf"
echo "配置文件 : $CONF"
grep -E '^(MODE|FIXED_FREQ|SCREEN_ON_FREQ|SCREEN_OFF_FREQ|POLL_INTERVAL)=' "$CONF" 2>/dev/null

exit 0
