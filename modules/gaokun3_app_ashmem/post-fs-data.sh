#!/system/bin/sh
# gaokun3 应用 ashmem SELinux 修复（KernelSU 模块）
#
# ── 症状 ────────────────────────────────────────────────────────────────────
# Edge 155（com.microsoft.emmx）点图标 → 闪现启动画面 → 立刻回桌面。
# 没有崩溃弹窗、没有 ANR、crash buffer 里什么都没有，进程是"干净退出"的：
#
#   E ashmem  : Unable to open ashmem device: Permission denied
#   E chromium: [ERROR:components/history/core/browser/history_service.cc:2019]
#               HistoryService::Init() failed by way of VisitDelegate::Init failing
#   I Zygote  : Process 17592 exited cleanly (0)
#
# am_proc_bound 后 0.2~0.3 秒就 am_proc_died，tombstone 一个都没有。
#
# ── 根因 ────────────────────────────────────────────────────────────────────
# SELinux denial：
#
#   avc: denied { open } for path="/dev/ashmemdec3e404-1674-4200-929e-ac35962058e9"
#     scontext=u:r:untrusted_app:s0:c40,c257,c512,c768
#     tcontext=u:object_r:ashmem_libcutils_device:s0
#     tclass=chr_file permissive=0  app=com.microsoft.emmx
#
# plat_sepolicy.cil 里 ashmem 的 open 权限是按 targetSdk 拆域授予的：
#
#   (allow untrusted_app_34 ashmem_libcutils_device (chr_file (open)))
#   (allow untrusted_app_32 ...)
#   (allow untrusted_app_30 ...)
#   (allow untrusted_app_29 ...)
#   (allow untrusted_app_27 ...)
#   (allow untrusted_app_25 ...)
#
# 最高只到 untrusted_app_34。而 plat_seapp_contexts 里有一条：
#
#   user=_app minTargetSdkVersion=37 domain=untrusted_app type=app_data_file levelFrom=all
#
# Edge 155 的 targetSdk=37（minSdk=29），匹配不到任何 untrusted_app_3x 版本域，
# 落到【基础域 untrusted_app】—— 这个域在整份 plat_sepolicy.cil 里
# 一条 ashmem 规则都没有。于是 HistoryService::Init() 的 ashmem open 被拒，
# Chromium 判定为致命错误，主动退出。
#
# 同源问题此前已出现过两次，都是同一份 plat_sepolicy.cil 的授权遗漏：
#   - audioserver 域（全系统无声，见 gaokun3_audio_fix）
#   - hal_camera_default / cameraserver 域（相机打开即崩，见 gaokun3-camera-ashmem）
#
# ── 修复 ────────────────────────────────────────────────────────────────────
# 给 untrusted_app 基础域补 ashmem open。这样不管 targetSdk 怎么涨
# （35/36/37/38... 只要 seapp_contexts 没有对应版本域就都落基础域），
# 都不会再踩同一个坑。
#
# ⚠️ 只授 ashmem_libcutils_device，不授 ashmem_device：最小权限。
# 日志里被拒的 /dev/ashmem<uuid> 标签就是 ashmem_libcutils_device
# （plat_file_contexts:59），Chromium/Edge 只用这个节点。
#
# 后两条是 Chromium 启动时的探测，非致命，只为消除日志噪音：
#   qemu_hw_prop    —— Chromium 探测自己是否跑在模拟器里（读 ro.kernel.qemu）
#   proc_version    —— SentryDeviceInf 线程读 /proc/version

MODDIR=${0%/*}
SEPOLICY=/sys/fs/selinux/policy

until [ -f "$SEPOLICY" ]; do
    sleep 0.1
done

ksud sepolicy patch "allow untrusted_app ashmem_libcutils_device chr_file { open read write getattr map ioctl }"
ksud sepolicy patch "allow untrusted_app qemu_hw_prop file { read getattr open map }"
ksud sepolicy patch "allow untrusted_app proc_version file { read getattr open map }"
