# fix_screenrecorder_privapp

把 `MIUIScreenRecorder` 从 `/product/data-app` 迁移到 `/product/priv-app`，
使录屏应用拿到 signature 权限 `INTERNAL_SYSTEM_WINDOW`，修复 HyperOS 录屏时
`Adding window failed / SecurityException`。APK 本身未修改。

```bash
adb push fix_screenrecorder_privapp.zip /data/local/tmp/
adb shell su -c 'ksud module install /data/local/tmp/fix_screenrecorder_privapp.zip'
adb reboot
```
