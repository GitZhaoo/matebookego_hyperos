#!/system/bin/sh
# gaokun3 GPU 频率调度 —— service.sh（boot_completed 后执行）。
#
# 两种模式：
#   fixed    — 把 GPU min_freq 写为 FIXED_FREQ，然后退出。
#   dynamic  — 后台起一个轻量守护进程，轮询背光亮度判断屏幕状态：
#                亮屏 -> min_freq = SCREEN_ON_FREQ
#                息屏 -> min_freq = SCREEN_OFF_FREQ
#              主脚本立刻退出（不阻塞其他模块的 service.sh），守护进程留在后台。
#
# apply.sh 切换配置时会先杀旧守护进程（按 PID 文件），再调用本脚本。
#
# ⚠️ PATH 钉 /system/bin（同 post-fs-data.sh，避免 /vendor/bin toybox 权限问题）。
PATH=/system/bin:/system/xbin
export PATH

GPU=/sys/class/devfreq/3d00000.gpu
MODDIR=$(cd "$(dirname "$0")" && pwd)
PIDFILE=/data/adb/gaokun3_gpu_freq.pid
BACKLIGHT=/sys/class/backlight/ae96000.dsi.0/brightness

# ── 读配置 ────────────────────────────────────────────────────────
CONF=/data/adb/gaokun3_gpu_freq.conf
[ -f "$CONF" ] || CONF=$MODDIR/config.conf

getconf_val() {
    grep "^$1=" "$CONF" 2>/dev/null | head -1 | cut -d= -f2-
}

MODE=$(getconf_val MODE)
FIXED_FREQ=$(getconf_val FIXED_FREQ)
SCREEN_ON_FREQ=$(getconf_val SCREEN_ON_FREQ)
SCREEN_OFF_FREQ=$(getconf_val SCREEN_OFF_FREQ)
POLL_INTERVAL=$(getconf_val POLL_INTERVAL)

# 默认值兜底
: ${MODE:=fixed}
: ${FIXED_FREQ:=690000000}
: ${SCREEN_ON_FREQ:=690000000}
: ${SCREEN_OFF_FREQ:=270000000}
: ${POLL_INTERVAL:=2}

# GPU 节点不存在则跳过
[ -d "$GPU" ] || exit 0

# ── 工具函数 ──────────────────────────────────────────────────────

apply_freq() {
    echo "$1" > "$GPU/min_freq" 2>/dev/null
}

# 杀掉已有的守护进程（按 PID 文件）
kill_daemon() {
    if [ -f "$PIDFILE" ]; then
        oldpid=$(cat "$PIDFILE" 2>/dev/null)
        if [ -n "$oldpid" ] && kill -0 "$oldpid" 2>/dev/null; then
            kill "$oldpid" 2>/dev/null
            i=0
            while [ $i -lt 10 ] && kill -0 "$oldpid" 2>/dev/null; do
                sleep 0.3
                i=$((i + 1))
            done
        fi
        rm -f "$PIDFILE"
    fi
}

# ── fixed 模式 ────────────────────────────────────────────────────
if [ "$MODE" != "dynamic" ]; then
    kill_daemon
    apply_freq "$FIXED_FREQ"
    log -t gpu_freq "fixed 模式：min_freq=$(cat "$GPU/min_freq" 2>/dev/null)"
    exit 0
fi

# ── dynamic 模式：后台起守护进程 ──────────────────────────────────
kill_daemon

# 守护进程逻辑放在函数里，后台执行
gpu_freq_daemon() {
    # 初始假设亮屏
    apply_freq "$SCREEN_ON_FREQ"
    log -t gpu_freq "dynamic 守护进程启动：on=${SCREEN_ON_FREQ} off=${SCREEN_OFF_FREQ} interval=${POLL_INTERVAL}s"

    while true; do
        b=$(cat "$BACKLIGHT" 2>/dev/null)
        if [ "${b:-0}" -gt 0 ] 2>/dev/null; then
            cur=$(cat "$GPU/min_freq" 2>/dev/null)
            [ "$cur" != "$SCREEN_ON_FREQ" ] && apply_freq "$SCREEN_ON_FREQ"
        else
            cur=$(cat "$GPU/min_freq" 2>/dev/null)
            [ "$cur" != "$SCREEN_OFF_FREQ" ] && apply_freq "$SCREEN_OFF_FREQ"
        fi
        sleep "$POLL_INTERVAL"
    done
}

# 后台启动守护进程，用 $! 记录真实 PID（POSIX shell 里子 shell 的 $$ 不可靠）。
# ⚠️ 守护进程的 stdout/stderr 必须重定向到 /dev/null，否则调用方（如 apply.sh
#    经 ksu.exec）会因 stdout pipe 不关闭而一直挂起等待。
gpu_freq_daemon >/dev/null 2>&1 &
DAEMON_PID=$!
echo "$DAEMON_PID" > "$PIDFILE"

log -t gpu_freq "service.sh 退出，守护进程 pid=$DAEMON_PID"
exit 0
