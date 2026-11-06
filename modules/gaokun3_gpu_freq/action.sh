#!/system/bin/sh
# gaokun3 GPU 频率调度 —— action.sh
#
# 由 `ksud module action gaokun3_gpu_freq` 触发（WebUI 调用，异步执行不阻塞）。
# 读取当前配置，按需启动或停止 dynamic 守护进程。
#
# ⚠️ PATH 钉 /system/bin（同其他脚本）。
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
SCREEN_ON_FREQ=$(getconf_val SCREEN_ON_FREQ)
SCREEN_OFF_FREQ=$(getconf_val SCREEN_OFF_FREQ)
POLL_INTERVAL=$(getconf_val POLL_INTERVAL)
: ${MODE:=fixed}
: ${SCREEN_ON_FREQ:=690000000}
: ${SCREEN_OFF_FREQ:=270000000}
: ${POLL_INTERVAL:=2}

[ -d "$GPU" ] || exit 0

# ── 杀掉已有守护进程 ──────────────────────────────────────────────
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

# ── fixed 模式：不需要守护进程，到此结束 ──────────────────────────
if [ "$MODE" != "dynamic" ]; then
    log -t gpu_freq "action: fixed 模式，已停止守护进程"
    exit 0
fi

# ── dynamic 模式：起守护进程 ──────────────────────────────────────
# 守护进程逻辑：轮询背光，亮屏写 ON_FREQ，息屏写 OFF_FREQ
gpu_freq_daemon() {
    while true; do
        b=$(cat "$BACKLIGHT" 2>/dev/null)
        if [ "${b:-0}" -gt 0 ] 2>/dev/null; then
            cur=$(cat "$GPU/min_freq" 2>/dev/null)
            [ "$cur" != "$SCREEN_ON_FREQ" ] && echo "$SCREEN_ON_FREQ" > "$GPU/min_freq" 2>/dev/null
        else
            cur=$(cat "$GPU/min_freq" 2>/dev/null)
            [ "$cur" != "$SCREEN_OFF_FREQ" ] && echo "$SCREEN_OFF_FREQ" > "$GPU/min_freq" 2>/dev/null
        fi
        sleep "$POLL_INTERVAL"
    done
}

# 后台启动，stdout/stderr 重定向到 /dev/null，用 $! 记录 PID
gpu_freq_daemon >/dev/null 2>&1 &
DAEMON_PID=$!
echo "$DAEMON_PID" > "$PIDFILE"

log -t gpu_freq "action: dynamic 守护进程已启动 (pid=$DAEMON_PID)"

# action.sh 本身可以立即退出（ksud action 是异步的，不阻塞 WebUI）
exit 0
