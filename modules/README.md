# 运行时模块（可选）

这些模块用于**不重刷 super** 的临时修复。正式部署的 `artifact/super.raw.img.zst`
已经包含同等核心修复，正常刷机后无需安装。

| 模块 | 作用 |
|---|---|
| `gaokun3_audio_fix` | SurfaceFlinger idle timer / drmhwc 日志 / SELinux 音频策略 |
| `gaokun3_gpu_freq` | GPU devfreq `min_freq`（可选 270–690 MHz） |
| `gaokun3_app_ashmem` | `untrusted_app` 基础域 ashmem open 权限（Edge 启动） |
| `fix_screenrecorder_privapp` | 录屏应用迁到 `priv-app`，修复窗口权限异常 |

打包并安装：

```bash
./deploy.sh modules
adb push artifact/modules/<module>.zip /data/local/tmp/
adb shell su -c 'ksud module install /data/local/tmp/<module>.zip'
adb reboot
```
