#!/system/bin/sh
# Debug service for the existing permissive mainline port; never clears buffers.
export PATH=/system/bin:/system/xbin:/vendor/bin
umask 077
base=/data/gaokun-bootlogs
[ -d "$base" ] && [ ! -L "$base" ] || exit 1
rm -rf "$base/previous2"
[ ! -d "$base/previous" ] || mv "$base/previous" "$base/previous2"
[ ! -d "$base/current" ] || mv "$base/current" "$base/previous"
mkdir "$base/current" || exit 1
out="$base/current"
chcon -R u:object_r:shell_data_file:s0 "$base"
exec >> "$out/collector.txt" 2>&1
date
cat /proc/sys/kernel/random/boot_id > "$out/boot-id.txt"
cat /proc/cmdline > "$out/cmdline.txt"
uname -a > "$out/uname.txt"
getprop > "$out/properties-start.txt"
dmesg > "$out/dmesg-start.txt" 2>&1
logcat -b all -v threadtime -v uid -f "$out/logcat.txt" -r 4096 -n 8 '*:V' &
log_pid=$!
trap 'kill "$log_pid" 2>/dev/null; sync' EXIT
timeout 8 logcat -d -b all -v threadtime '*:V' | head -c 8388608 > "$out/logcat-start.txt"
echo 'gaokun: persistent boot logger active at /data/gaokun-bootlogs/current' > /dev/kmsg
sync
i=0
completed_ticks=0
# At most 20 minutes plus bounded diagnostic calls; stop 60s after boot completes.
while [ "$i" -lt 240 ]; do
    sleep 5
    i=$((i + 1))
    dmesg > "$out/dmesg-next.txt" 2>&1
    mv "$out/dmesg-next.txt" "$out/dmesg-latest.txt"
    if [ $((i % 4)) -eq 0 ]; then
        {
            date
            cat /proc/uptime
            getprop
            ps -A -o USER,PID,PPID,NAME,STAT,ARGS
            cat /proc/mounts
            ls -l /sys/fs/bpf/netd_shared
            ls -lt /data/tombstones /data/anr /data/system/dropbox
        } > "$out/state-next.txt" 2>&1
        mv "$out/state-next.txt" "$out/state-latest.txt"
    fi
    # Binder probes are bounded so a hung system_server cannot block collection.
    case "$i" in
        6|18|36)
            timeout 6 service list > "$out/services-$i.txt" 2>&1
            timeout 8 dumpsys -t 5 display > "$out/display-$i.txt" 2>&1
            timeout 6 cmd overlay list > "$out/overlays-$i.txt" 2>&1
            cat /sys/class/backlight/*/brightness /sys/class/backlight/*/max_brightness > "$out/backlight-$i.txt" 2>&1
            timeout 8 dumpsys -t 5 activity processes > "$out/activity-$i.txt" 2>&1
            timeout 8 dumpsys -t 5 SurfaceFlinger > "$out/surfaceflinger-$i.txt" 2>&1
            ;;
    esac
    sync
    if [ "$(getprop sys.boot_completed)" = 1 ]; then
        completed_ticks=$((completed_ticks + 1))
        [ "$completed_ticks" -lt 12 ] || break
    else
        completed_ticks=0
    fi
    if ! kill -0 "$log_pid" 2>/dev/null; then
        echo 'logcat exited; restarting reader without clearing buffers'
        logcat -b all -v threadtime -v uid -f "$out/logcat.txt" -r 4096 -n 8 '*:V' &
        log_pid=$!
    fi
done
date
echo "Collector finished: iteration=$i boot_completed=$(getprop sys.boot_completed)"
