#!/system/bin/sh
# gaokun3 应用 ashmem SELinux 修复 —— service 阶段重放。
#
# post-fs-data.sh 里已经打过补丁，这里再打一次是双保险：
# ksud sepolicy patch 是运行时注入，某些启动时序下 post-fs-data 阶段的
# 注入可能被后续策略重载覆盖。service 阶段在所有 HAL 和 zygote fork 之前，
# 此时补一次能确保应用进程拿到权限。
#
# 注意：这里只有 ashmem_libcutils_device，没有 ashmem_device —— 日志里被拒的
# 就是 ashmem_libcutils_device 这个标签，按最小权限只授它，详见 post-fs-data.sh。

SEPOLICY=/sys/fs/selinux/policy

until [ -f "$SEPOLICY" ]; do
    sleep 0.1
done

ksud sepolicy patch "allow untrusted_app ashmem_libcutils_device chr_file { open read write getattr map ioctl }"
ksud sepolicy patch "allow untrusted_app qemu_hw_prop file { read getattr open map }"
ksud sepolicy patch "allow untrusted_app proc_version file { read getattr open map }"

exit 0
