#!/system/bin/sh
# Runs at post-fs-data, before SurfaceFlinger starts, so these take effect on
# the very first boot with the module enabled.
#
# 1) SurfaceFlinger idle down-clocking.
#    Default behaviour drops renderRate to 20 Hz when the screen goes idle and
#    only recovers on the next touch. Measured on Settings list scroll:
#      dumpsys SurfaceFlinger      -> renderRate oscillated 120 -> 20 -> 120
#      dumpsys gfxinfo framestats  -> FrameInterval pinned at 50.00 ms (20 fps)
#                                     for all 120 sampled frames
#    With idle/touch timers pinned high and frame-rate override off:
#      14 consecutive samples during scroll all 120.00 Hz, and still 120.00 Hz
#      after 20 s idle.
setprop debug.sf.set_idle_timer_ms 1000000
setprop debug.sf.set_touch_timer_ms 1000000
setprop debug.sf.enable_frame_rate_override false

# 2) drm_hwcomposer log spam.
#    drmhwc logs "Encountered multiple cursor planes for CRTC 90. Ignoring
#    plane 84" on every validate cycle -- measured 2230 lines per 30 s
#    (74 lines/s) while idle. It is harmless (the duplicate cursor plane is
#    simply skipped and DrmKmsPlan still succeeds; "Failed to create
#    DrmKmsPlan" count is 0), but it floods logd. Raising the tag to ERROR
#    dropped drmhwc output to 0 lines/10 s and total log volume from 15257 to
#    6091 lines per 30 s (-60%).
setprop log.tag.drmhwc E
