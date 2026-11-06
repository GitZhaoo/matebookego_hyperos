# gaokun3_app_ashmem

修复 HyperOS 4 上 `targetSdk=37` 的应用（典型：Microsoft Edge 155）落进基础
`untrusted_app` 域后，打开 `/dev/ashmem*` 被 SELinux 拒绝、进程“干净退出”的问题。

系统 super 已包含等价策略（见 `docs/edge-ashmem-fix.md`）。仅在不想重刷
`super` 时安装本模块。

```bash
adb push gaokun3_app_ashmem.zip /data/local/tmp/
adb shell su -c 'ksud module install /data/local/tmp/gaokun3_app_ashmem.zip'
adb reboot
```

打包：

```bash
./deploy.sh modules
```
