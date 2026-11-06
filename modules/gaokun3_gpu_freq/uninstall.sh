#!/system/bin/sh
# gaokun3 GPU 频率调度 —— 卸载时恢复 GPU min_freq 到默认最低档。
PATH=/system/bin:/system/xbin
export PATH

GPU=/sys/class/devfreq/3d00000.gpu
PIDFILE=/data/adb/gaokun3_gpu_freq.pid

# 杀守护进程
if [ -f "$PIDFILE" ]; then
    pid=$(cat "$PIDFILE" 2>/dev/null)
    [ -n "$pid" ] && kill "$pid" 2>/dev/null
    rm -f "$PIDFILE"
fi

# 恢复 min_freq 到默认最低档（270 MHz）
[ -d "$GPU" ] && echo 270000000 > "$GPU/min_freq" 2>/dev/null

# 清理持久配置（可选：保留的话下次重装同模块自动恢复设置）
# rm -f /data/adb/gaokun3_gpu_freq.conf

log -t gpu_freq "模块卸载，min_freq 已恢复为 270000000"
exit 0
