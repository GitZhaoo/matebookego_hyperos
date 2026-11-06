#!/system/bin/sh
# gaokun3 HyperOS audio & display runtime tuning.
#
# GPU min_freq 锁频已拆分到独立模块 gaokun3_gpu_freq，本脚本不再处理 GPU。
#
# NOTE: speaker volume is deliberately NOT touched here. An earlier revision
# forced STREAM_MUSIC to 0 on every boot; that was removed at the user's
# request so the persisted user volume is respected. The mixer PA gain is
# likewise left to audioroute.sh, which runs at sys.boot_completed and sets
# SpkrLeft/Right PA Volume to 21.

# SurfaceFlinger idle down-clocking (primary copy lives in post-fs-data.sh so
# it is active before SurfaceFlinger starts; repeated here as a safety net).
setprop debug.sf.set_idle_timer_ms 1000000
setprop debug.sf.set_touch_timer_ms 1000000
setprop debug.sf.enable_frame_rate_override false
setprop log.tag.drmhwc E

exit 0
