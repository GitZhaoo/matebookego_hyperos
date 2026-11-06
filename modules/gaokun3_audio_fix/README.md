# KernelSU 模块：gaokun3 HyperOS 音频与显示修复

这是 `docs/audio-and-performance-fixes.md` 里音频与显示修复的**运行时版本**，
适合已经刷好系统、不想重新构建刷机的场景。

重新刷入含 `scripts/build.py` 改动的 super 后，音频 sepolicy 部分可以删掉。

## 内容

| 文件 | 作用 |
|---|---|
| `module.prop` | 模块元信息 |
| `sepolicy.rule` | audioserver 的 ashmem / prop 访问权限（修无声 + 视频黑屏） |
| `post-fs-data.sh` | SF 启动前设置 idle timer / frame-rate override / `log.tag.drmhwc` |
| `service.sh` | 运行时重复设置 SF idle timer / drmhwc 日志（兜底） |

## 已拆分

GPU 频率调度（`min_freq` 锁频）已拆分到独立模块 `gaokun3_gpu_freq`，
支持 8 档频率选择和息屏/亮屏动态切换。如需 GPU 调频，请安装该模块。

## 打包

⚠️ **`module.prop` 必须是 zip 里的第一个条目**。`ksud module install` 按条目
顺序解压，如果 `module.prop` 不在首位，它解压完就停止，其余文件全部丢失
（表现为模块目录里只有 `module.prop`，修复不生效）。

```bash
cd modules/gaokun3_audio_fix
zip -X ../../gaokun3_audio_fix.zip module.prop
zip -X -g ../../gaokun3_audio_fix.zip sepolicy.rule service.sh post-fs-data.sh
```

## 安装

```bash
adb push gaokun3_audio_fix.zip /data/local/tmp/
adb shell su -c 'ksud module install /data/local/tmp/gaokun3_audio_fix.zip'
adb reboot
```

## 更新（覆盖安装不可靠）

```bash
adb shell su -c 'rm -rf /data/adb/modules/gaokun3_audio_fix /data/adb/modules_update/gaokun3_audio_fix'
adb shell su -c 'ksud module install /data/local/tmp/gaokun3_audio_fix.zip'
adb reboot
```

## 卸载

```bash
adb shell su -c 'rm -rf /data/adb/modules/gaokun3_audio_fix'
adb reboot
```

## 验证

```bash
adb shell su -c 'logcat -d | grep -c "createTrack_l.*-12"'   # 期望 0
adb shell su -c 'getprop debug.sf.set_idle_timer_ms'          # 期望 1000000
adb shell su -c 'getprop log.tag.drmhwc'                      # 期望 E
adb shell su -c 'dumpsys SurfaceFlinger | grep renderRate'    # 期望 120.00 Hz
```

## 注意

- 模块**不改扬声器音量**，开机沿用用户上次的设定。
- `service.sh` 只设 SF 属性，不动 PA 增益 —— 后者由系统自带的
  `audioroute.sh` 在 `sys.boot_completed=1` 时设为 21（正常值）。
- 不要为了「重置音频」反复 `killall audioserver` 或 unbind SoundWire 驱动，
  会造成 port 泄漏（`All ports busy`），只能重启恢复。
- GPU 频率调度请使用 `gaokun3_gpu_freq` 模块。
