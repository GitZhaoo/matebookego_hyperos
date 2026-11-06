# 音频与性能问题修复教程

本文记录 MateBook E Go（gaokun3）刷入 HyperOS 4（Pad9 yupei 底包）后遇到的
三类问题：**全系统无声 / 视频黑屏**、**UI 卡顿**、**扬声器与麦克风**，以及
每一类的定位过程、根因、修复方法与验证数据。

所有修复都已落到本仓库，重新构建刷机后不需要额外操作。KernelSU 模块
`modules/gaokun3_audio_fix/` 是给**不重新刷机**的场景准备的临时手段。

---

## 0. 环境前提

- 设备：HUAWEI MateBook E Go（SC8280XP / gaokun3），已刷 crDroid 16 vendor
- 系统：HyperOS 4（`OS4.0.10.0.XPZCNXM`，Android 17）
- 内核：`7.2.9-gaokun3+`（mainline + gaokun patches）
- Root：ReSukiSU（KernelSU 分支），**内置在 kernel 里**
- SELinux：`Enforcing`（注意 `ro.boot.selinux=permissive` 与实际
  `getenforce=Enforcing` 不一致，属移植遗留）

> ⚠️ 下文所有 `adb shell` 命令默认走 `su -c`。如果 `su` 不可用，先在
> ReSukiSU 里给 `com.android.shell` 授权。
>
> ⚠️ ReSukiSU 管理器版本必须与内核内置的 KSU 驱动匹配。本机内核编入的是
> rc1，装 rc3 会提示「需要更新内核」且无法授权。用
> `input/ReSukiSU_v4.2.0-rc1_35061-arm64-v8a-release.apk`。

---

## 1. 问题一：全系统无声 + 视频黑屏

### 症状

- 任何应用播放音频都没有声音
- 红果短剧（`com.phoenix.read`）进入播放页后：**UI 正常、视频区纯黑**
- `logcat` 每秒刷几十次 `createTrack_l` 失败

### 定位过程

**第一步：确认不是音量、不是路由**

```bash
# 音频 HAL 报告的设备是正常的
adb shell su -c 'dumpsys media.audio_policy | grep -A15 "Available output devices"'
# → Port ID: 2; "Speaker"; {AUDIO_DEVICE_OUT_SPEAKER, @:CARD_0_DEV_1}
```

**第二步：抓 AudioTrack 的真实错误**

```bash
adb shell su -c 'logcat -d | grep -E "createTrack_l|control block" | tail -10'
```

输出：

```
E AudioFlinger: createTrack_l() initCheck failed -12; no control block?
E AudioTrack: createTrack_l(0): AudioFlinger could not create track, status: -12 output 0
```

`-12` = `ENOMEM`。AudioFlinger 分配不出 AudioTrack 的**控制块**。

**第三步：找 SELinux 拒绝**

```bash
adb shell su -c 'logcat -d | grep "avc:.*denied" | grep -i ashmem | tail -5'
```

输出：

```
avc: denied { open } for path="/dev/ashmem59fb3bf8-..."
  scontext=u:r:audioserver:s0
  tcontext=u:object_r:ashmem_libcutils_device:s0
  tclass=chr_file permissive=0
```

**根因确认**：`audioserver` 域打开 `/dev/ashmem` 被拒 → AudioFlinger 拿不到
共享内存控制块 → `createTrack_l()` 返回 -12 → **全系统建不出音轨**。

### 为什么红果短剧会黑屏

字节系播放器（`libttmplayer.so`）是**音频主时钟**架构：

```
AudioTrack 创建失败
  → 没有音频时钟
  → 播放器不启动视频解码
  → SurfaceView 已创建但没有帧
  → 界面正常、视频区纯黑
```

实测修复前 AudioTrack 失败频率是 **47 次/秒**（死循环重试），CPU 占用 52%。

### 根因细节

`plat_sepolicy.cil` 里只有：

```cil
(allow appdomain ashmem_libcutils_device (chr_file (execute)))
```

**`audioserver` 域一条 ashmem 规则都没有**。项目此前的 `build.py` 只给
`system_server` 和 `hal_audio_default` 加了规则，漏了 `audioserver`。

### 修复

在 `scripts/build.py` 的 `policy()` 里追加：

```cil
(allow audioserver ashmem_libcutils_device (chr_file (open read write getattr map ioctl)))
(allow audioserver ashmem_device (chr_file (open read write getattr map ioctl)))
(allow audioserver bootanim_system_prop (file (read getattr map)))
(allow audioserver vendor_default_prop (file (read getattr map open)))
```

后两条是 audioserver 初始化输出设备时读的属性。

### 验证

```bash
# 1. 音轨能建出来（Global session refs 有内容）
adb shell su -c 'dumpsys media.audio_flinger | grep -A3 "Global session refs"'

# 2. 不再有 -12
adb shell su -c 'logcat -d | grep -c "createTrack_l.*-12"'   # 应为 0

# 3. 红果短剧正常播放（看画面推进）
```

---

## 2. 问题二：UI 卡顿

这个问题有**三层**独立原因，必须全部修掉。只修其中一层会感觉「好像好了一点
但还是卡」。

### 2.1 第一层：刷新率停在 60 Hz 的 display mode

**症状**：`dumpsys SurfaceFlinger` 里 `Composition efficiency` 只有 0.48，
多个全屏层 `forceClientComposition=true`。

**定位**：

```bash
adb shell su -c 'dumpsys SurfaceFlinger | grep -E "activeMode=|Composition efficiency"'
# → activeMode={id=1, hwcId=3, vsyncRate=60.00 Hz ...}   ← 停在 60Hz 模式
# → Composition efficiency: 0.485535
```

面板有两个 mode：

| mode | hwcId | 刷新率 |
|---|---|---|
| `id=0` | `hwcId=2` | 120 Hz |
| `id=1` | `hwcId=3` | 60 Hz |

**根因**：HyperOS 的 `MiuiRefreshRatePolicy` 以 `RenderVote` 形式给
`DisplayModeDirector` 投票，读的是 **secure 命名空间**的 `miui_refresh_rate`
和 `user_refresh_rate`。AOSP 的 `system.peak_refresh_rate` 对它**无效**。

停在 60 Hz 后，DPU 只给 1 个 plane，其余层被 drm_hwcomposer 判为
`Failed to create DrmKmsPlan`，全部回退 GPU client 合成。

**修复**：

```bash
adb shell su -c 'settings put secure miui_refresh_rate 120'
adb shell su -c 'settings put secure user_refresh_rate 120'
adb shell su -c 'settings --user 0 put system is_smart_fps 0'
adb shell su -c 'settings --user 0 put system min_refresh_rate 120.0'
adb shell su -c 'settings --user 0 put system peak_refresh_rate 120.0'
adb shell su -c 'setprop ctl.restart surfaceflinger'   # 必须，否则当前 session 不切
```

同时关掉小米的背景模糊（各占一个全屏层，8-plane 的 DPU 吃不消）：

```bash
adb shell su -c 'settings put secure disable_window_blurs 1'
adb shell su -c 'settings put global disable_window_blurs 1'
adb shell su -c 'settings put global support_dynamic_island_blur 0'
adb shell su -c 'settings put secure miui_home_recents_blur_mode 0'
```

**验证**：

```bash
adb shell su -c 'dumpsys SurfaceFlinger | grep -E "activeMode="'
# → activeMode={id=0, hwcId=2, ... vsyncRate=120.00 Hz ...}   ✅
```

### 2.2 第二层：GPU 不升频

**症状**：合成正常了，但滑动时 GPU 始终 270 MHz。

**定位**：

```bash
# 滑动时密集采样
adb shell 'for i in 1 2 3 4 5 6; do input swipe 400 1500 400 400 80; done' &
for i in $(seq 1 10); do
  adb shell su -c 'cat /sys/class/devfreq/3d00000.gpu/cur_freq'
  sleep 0.3
done
# → 全是 270000000 / 547000000，从不升到 606 以上
```

**根因**：mainline msm 的 GPU devfreq 只有 `simple_ondemand`：

```bash
adb shell su -c 'cat /sys/class/devfreq/3d00000.gpu/available_governors'
# → simple_ondemand   （只有这一个）
```

内核里 `CONFIG_DEVFREQ_GOV_PERFORMANCE=m`、`CONFIG_DEVFREQ_GOV_USERSPACE=m`，
但设备上**没有对应的 .ko**，所以加载不了。`simple_ondemand` 的负载采样在
1600×2560@120Hz 的 UI 负载下升不上去。

**修复**：把 `min_freq` 钉在最高档。

```bash
adb shell su -c 'echo 690000000 > /sys/class/devfreq/3d00000.gpu/min_freq'
```

实测对比（Settings 列表连续滑动）：

| `min_freq` | 90th | 95th | Missed Vsync |
|---|---:|---:|---:|
| 270 MHz（默认） | 13 ms | 18 ms | 3 |
| 547 MHz | 15 ms | 18 ms | 1 |
| **690 MHz** | **5 ms** | **5–6 ms** | **0** |

只有满频才把 120 Hz 下 8.33 ms 的预算用满，547 档不够。

### 2.3 第三层：SurfaceFlinger 空闲降频到 20 Hz

**这是最隐蔽的一层，也是「应用内滑动仍然卡」的主因。**

**症状**：`renderRate` 在 120 和 20 之间反复横跳，滑一下卡一下。

**定位方法一：逐帧解析**

```bash
adb shell 'dumpsys gfxinfo com.android.settings reset'
adb shell 'for i in 1 2 3 4 5 6 7 8; do input swipe 400 1600 400 600 70; done'
adb shell 'dumpsys gfxinfo com.android.settings framestats'
```

解析 `FrameInterval` 列：

```
FrameInterval  p50=50.00ms  p90=50.00ms  p99=50.00ms
```

**120 帧全部是 50 ms 间隔 = 20 fps**。而 `DequeueBufferDuration` p50 只有
0.02 ms —— 取缓冲完全不慢，是**被节流**了。

**定位方法二：实时采样刷新率**

```bash
adb shell 'for i in 1 2 3 4 5 6 7 8; do input swipe 400 1600 400 600 70; done' &
for i in $(seq 1 10); do
  adb shell "dumpsys SurfaceFlinger | grep -oE 'renderRate=[0-9.]+ Hz' | head -1"
  sleep 0.35
done
```

输出：

```
renderRate=120.00 Hz
renderRate=120.00 Hz
renderRate=20.00 Hz     ← 掉下去了
renderRate=20.00 Hz
renderRate=20.00 Hz
...
```

每次触摸升到 120 Hz，**松手立刻掉回 20 Hz**。

**定位方法三：看 setDesiredMode 日志**

```bash
adb shell su -c 'logcat -d -s SurfaceFlinger | grep setDesiredMode | tail -8'
```

```
setDesiredMode 0 {mode={fps=120.00 Hz ...}}
setDesiredMode 0 {mode={fps=20.00 Hz ...}}
setDesiredMode 0 {mode={fps=120.00 Hz ...}}
```

秒级交替。

**根因**：SurfaceFlinger 的 idle timer。无触摸时把 `renderRate` 压到 20 Hz，
恢复又不够快，导致滑动全程跑在 20 fps 上。

> 💡 注意 `MiuiRefreshRatePolicy` 的 `PRIORITY_MIUI_REFRESH_RATE` 投票上限
> 已经是 120，`min_refresh_rate=120` 也已写入，但**都管不到 idle timer**。
> 这是为什么 2.1 修完后仍然卡。

**修复**：

```bash
adb shell su -c 'setprop debug.sf.set_idle_timer_ms 1000000'
adb shell su -c 'setprop debug.sf.set_touch_timer_ms 1000000'
adb shell su -c 'setprop debug.sf.enable_frame_rate_override false'
adb shell su -c 'setprop ctl.restart surfaceflinger'
```

> ⚠️ 这三个属性由 SurfaceFlinger **启动时读取**。`setprop` 后必须重启 SF
> （或重启设备）才生效。写进 init rc 时位置要在 `on post-fs-data`（早于 SF）。

**验证**：

```bash
# 滚动中连续采样，应全部 120.00 Hz
adb shell 'for i in 1 2 3 4 5 6 7 8 9 10; do input swipe 400 1600 400 600 60; done' &
for i in $(seq 1 14); do
  adb shell "dumpsys SurfaceFlinger | grep -oE 'renderRate=[0-9.]+ Hz' | head -1"
  sleep 0.4
done
# 静止 20 秒后再看一次，仍是 120.00 Hz
```

### 2.4 三层都修完后的实测

| 指标 | 修复前 | 修复后 |
|---|---:|---:|
| 90th 百分位 | 13 ms | **6–7 ms** |
| 95th | 24 ms | **7–8 ms** |
| 99th | 85 ms | **14–21 ms** |
| Missed Vsync | 27 | **0** |
| Janky | 17.25% | **0.12–0.72%** |
| `renderRate` | 120/20 横跳 | **恒定 120 Hz** |

### 2.5 曾怀疑但已排除的项

排查过程中一度怀疑下面几项，复核后确认**不是卡顿主因**，记录在此避免重复
走弯路。

**（1）ANGLE `submitCommands` 阻塞**

哔哩哔哩 ANR trace 里 RenderThread 停在：

```
#01 libGLESv2_angle.so  rx::vk::CommandQueue::submitCommands(...)
#10 libhwui.so          EglManager::createReleaseFence()
#15 libhwui.so          DrawFrameTask::syncFrameState()
```

这是**结果而非原因**：帧被 idle timer 节流到 20 fps 后，主线程在
`ThreadedRenderer.syncAndDrawFrame` 等 RenderThread，RenderThread 又在等
Vulkan 队列排空。idle timer 修好后该栈不再出现。

> 补充硬约束：本机 vendor 分区**没有原生 GLES 驱动**
> （`/vendor/lib64/egl/` 不存在），渲染只有 ANGLE→Vulkan→turnip 一条路，
> 没有回退可选。所以 `persist.graphics.egl=angle` 是唯一可行配置。

**（2）TelephonyManager 异常**

```
E TelephonyManager: java.lang.IllegalStateException: telephony service is null.
  at AmlWifiScoreReportInjector.isMobileDataDisabled()
```

小米 Wi-Fi 评分器每次打分都调 `TelephonyManager.isDataEnabled()`，本机无
modem。实测 **9 次 / 30 秒**，量级远小于日志刷屏，**不是卡顿主因**，暂不处理。

**（3）`app duration` 与 `SF duration` 不匹配**

```
app duration: 15666682 ns   (63.8 Hz)
SF duration:   7333341 ns   (136 Hz)
```

试过 `debug.sf.early.app.duration` 等属性，**无效** —— 该值由已激活的
display mode 推导，不由 prop 控制。`renderRate` 已是 120 Hz，属调度估算值
偏差，不影响实际出帧。

**（4）`com.android.phone` 启动期 ANR**

开机时有一批 `failed to complete startup`（`/data/anr/anr_*`），之后
`com.qti.phone` 正常驻留，未复发。与 README 记录的 ExtTelephonyManager
加载问题同源，属已知遗留。

---

## 3. 问题三：日志刷屏（附带发现，值得修）

### 症状

系统日志量异常大：**30 秒 15257 行**（约 508 行/秒）。

### 定位

```bash
adb shell su -c 'logcat -d | awk "{print \$6}" | sort | uniq -c | sort -rn | head -10'
```

```
2230 drmhwc
2124 miuix_anim:
1328 libc
1122 MI-SF
 801 MIUIInput:
```

`drmhwc` 排第一。

```bash
adb shell su -c 'logcat -d -s drmhwc | tail -3'
```

```
W drmhwc: Encountered multiple cursor planes for CRTC 90. Ignoring plane 84
W drmhwc: Encountered multiple cursor planes for CRTC 90. Ignoring plane 84
W drmhwc: Encountered multiple cursor planes for CRTC 90. Ignoring plane 84
```

**74 行/秒**，但同一时间：

```bash
adb shell su -c 'logcat -d -s drmhwc | grep -c "Failed to create DrmKmsPlan"'
# → 0
```

合成**完全正常**，重复的 cursor plane 只是被跳过。纯属噪音。

### 修复

```bash
adb shell su -c 'setprop log.tag.drmhwc E'
```

标准 Android log 级别控制。验证：

```bash
adb shell su -c 'logcat -c'; sleep 10
adb shell su -c 'logcat -d -s drmhwc | wc -l'
# → 0
```

效果：系统总日志量 **15257 → 6091 行/30 秒（-60%）**。

---

## 4. 问题四：扬声器与麦克风

### 4.1 扬声器

**硬件本身正常**。音频通路：

| 用途 | PCM | 通路 |
|---|---|---|
| 扬声器 | `hw:0,1` | `WSA_CODEC_DMA_RX_0 ← MultiMedia2` |
| 耳机 | `hw:0,0` | `RX_CODEC_DMA_RX_0 ← MultiMedia1` |
| 头戴麦 | `hw:0,2` | `TX_CODEC_DMA_TX_3 → MultiMedia3` |
| 内置麦 | `hw:0,3` | `VA_CODEC_DMA_TX_0 → MultiMedia4` |

路由由系统自带的 `audioroute.sh` 在 `sys.boot_completed=1` 时设置。它会把
`SpkrLeft/Right PA Volume` 写为 **21**（= +6 dB，正常值）。

**「没声音」的真正原因是第 1 节那个 ashmem 问题** —— 根本没有音频流到达功放。
ashmem 修好后扬声器即正常。

**常见误判**：

```bash
# 这两颗功放长期处于 Alert 状态，刷 "Bus clash detected"
adb shell su -c 'cat /sys/bus/soundwire/devices/sdw:1:0:0217:0202:00:1/status'
# → Alert
```

crDroid 基线上同样如此，**不影响出声**，不要为此去动 SoundWire。

> ⚠️⚠️ **千万不要**为了「重置」而反复 `killall audioserver` 或 unbind
> `qcom-soundwire` / `snd-sc8280xp` 驱动。这会导致 **SoundWire port 泄漏**：
>
> ```
> qcom-soundwire 3250000.soundwire: All ports busy
> WSA Playback: ASoC error (-16): at __soc_pcm_hw_params()
> ```
>
> 之后 `pcmC0D1p` 永远打不开（`Device or resource busy`），**只能重启恢复**，
> 且驱动 rebind 会失败（`--- no soundcards ---`）。

**音量说明**：本仓库**不改扬声器音量**。开机沿用用户上次的设定。

### 4.2 麦克风

**硬件正常**，直接验证：

```bash
adb shell su -c 'tinycap /data/local/tmp/mic.wav -D 0 -d 3 -c 2 -r 48000 -b 16 -T 3'
adb shell su -c 'od -A d -t d2 -j 44 -N 40 /data/local/tmp/mic.wav'
# → 10721  18247  10512  17891 ...   有真实波形，不是静音
```

应用层录音同样受第 1 节 ashmem 问题影响，修好后打通。

> ⚠️ 排查时不要用 `-d 1` 测扬声器：`pcmC0D1p` 被 AudioFlinger 独占时
> `tinyplay` 会报 `cannot open device 1`。这是**预期行为**，不是故障。

---

## 5. 项目落地清单

所有修复都已写进本仓库。重新构建刷入 super 后**不需要 KernelSU 模块**。

| 修复 | 落地位置 |
|---|---|
| audioserver ashmem / prop 权限 | `scripts/build.py` → `policy()` → `plat_sepolicy.cil` |
| SF idle timer / frame-rate override | `scripts/build.py` → `gaokun-hyperos.rc` 的 `on post-fs-data` |
| `log.tag.drmhwc=E` | 同上 |
| GPU `min_freq=690MHz` | 同上，`on property:sys.boot_completed=1` |
| 刷新率（secure 命名空间） | 同上，`exec` 调 `system/etc/gaokun-refresh.sh` |
| `config_defaultRefreshRate=120` | `assets/overlay/res/values/config.xml` |
| 首次显示配置 | `scripts/configure_display.py`（写 userdata，需手动跑一次） |

### 为什么 `gaokun-refresh.sh` 要单独成文件

`settings` 是 binder 调用，**init 自身域没有权限**。用
`exec - root root -- /system/bin/sh /system/etc/gaokun-refresh.sh` 起来后，
进程落到项目已有的 `gaokun_bootdiag`（`typepermissive` 域）就能写。

### 重刷流程

```bash
python3 scripts/overlay.py
docker exec pad9-port-build python3 scripts/build.py adapt
docker exec pad9-port-build python3 scripts/pack_super.py --output out --report-dir reports
docker exec pad9-port-build img2simg out/super.raw.img out/super.img
docker exec pad9-port-build zstd -T4 -3 -f out/super.raw.img -o out/super.raw.img.zst
# 刷入 super
python3 scripts/configure_display.py --serial 实际序列号
```

### 重刷后自检

```bash
# 1. audioserver 有 ashmem 权限（不再有 -12）
adb shell su -c 'logcat -d | grep -c "createTrack_l.*-12"'          # 期望 0

# 2. 120 Hz
adb shell su -c 'dumpsys SurfaceFlinger | grep -E "activeMode=|renderRate="'

# 3. GPU 满频
adb shell su -c 'cat /sys/class/devfreq/3d00000.gpu/min_freq'       # 期望 690000000

# 4. idle timer
adb shell su -c 'getprop debug.sf.set_idle_timer_ms'                # 期望 1000000

# 5. drmhwc 日志
adb shell su -c 'getprop log.tag.drmhwc'                            # 期望 E

# 6. 刷新率脚本跑起来了
adb shell su -c 'settings get secure miui_refresh_rate'             # 期望 120
```

---

## 6. KernelSU 模块（不重新刷机时用）

`modules/gaokun3_audio_fix/` 是把上述修复做成运行时补丁，适合**当前这台已经
刷好的机器**。

### 内容

| 文件 | 作用 |
|---|---|
| `module.prop` | 模块元信息（中文名称与说明） |
| `sepolicy.rule` | audioserver 的 ashmem / prop 访问权限 |
| `post-fs-data.sh` | SF 启动前：idle timer、frame-rate override、`log.tag.drmhwc` |
| `service.sh` | 运行时：GPU `min_freq` 690 MHz |

### 安装

```bash
cd modules
zip -X ../gaokun3_audio_fix.zip module.prop        # module.prop 必须在第一个！
zip -X -g ../gaokun3_audio_fix.zip sepolicy.rule service.sh post-fs-data.sh

adb push ../gaokun3_audio_fix.zip /data/local/tmp/
adb shell su -c 'ksud module install /data/local/tmp/gaokun3_audio_fix.zip'
adb reboot
```

### ⚠️ 打包陷阱（踩过）

`ksud module install` **按 zip 条目顺序解压**，`module.prop` 必须是压缩包里的
**第一个条目**。否则它解压完 `module.prop` 就停止，其余文件全部丢失 ——
表现为模块目录里只有 `module.prop`，脚本缺失、修复不生效。

覆盖安装同样不可靠（旧文件会被保留、新文件可能丢失）。改动模块内容时：

```bash
adb shell su -c 'rm -rf /data/adb/modules/gaokun3_audio_fix /data/adb/modules_update/gaokun3_audio_fix'
# 再重新 install
```

### 卸载

```bash
adb shell su -c 'rm -rf /data/adb/modules/gaokun3_audio_fix'
adb reboot
```

> 重新刷入含本文修复的 super 后，这个模块可以删掉。
>
> ⚠️ GPU 频率锁频已从本模块拆分到独立模块 `gaokun3_gpu_freq`（见下一节）。
> 卸载 `gaokun3_audio_fix` 不影响 GPU 调度，反之亦然。

---

## 6.5 GPU 频率调度独立模块 `gaokun3_gpu_freq`

### 为什么拆分

`gaokun3_audio_fix` 原本同时做三件事：audioserver ashmem sepolicy 注入、
SurfaceFlinger idle timer 修复、GPU `min_freq` 锁 690 MHz。其中 GPU 锁频是
在 SF idle timer 修复**之前**打的权宜之计，和音频修复无关，且用户希望 GPU
频率可配置（8 档可选）、支持息屏降频。因此拆成独立模块。

### GPU 现状（sc8280xp Adreno）

- devfreq 节点：`/sys/class/devfreq/3d00000.gpu`
- governor：只有 `simple_ondemand`（`performance`/`userspace` 编成 `=m` 但
  设备上无 `.ko`；高通 `msm-adreno-tz` 闭源，主线没有）
- 8 档频率：270 / 410 / 500 / 547 / 606 / 640 / 655 / 690 MHz
- `simple_ondemand` 的 50ms 轮询在 1600×2560@120Hz UI 滑动负载下升频不积极，
  GPU 只在 270/547 MHz 间跳。实测 gfxinfo（Settings 列表滚动）：

  | min_freq | 90th | missed vsync |
  |---:|---:|---:|
  | 270 MHz（默认） | 13 ms | 3 |
  | 547 MHz | 15 ms | 1 |
  | 690 MHz | 5–6 ms | 0 |

- 息屏检测节点：`/sys/class/backlight/ae96000.dsi.0/brightness`
  （灭屏=0，亮屏>0；`bl_power` 在本驱动不更新，不可用）

### 模块内容

路径：`modules/gaokun3_gpu_freq/`

| 文件 | 作用 | 执行时机 |
|---|---|---|
| `module.prop` | 模块元信息 | — |
| `config.conf` | 默认配置（模式 + 频率 + 轮询间隔） | 被脚本读取 |
| `post-fs-data.sh` | SF 启动前早期应用 min_freq | post-fs-data |
| `service.sh` | fixed 写入 / dynamic 起守护进程 | boot_completed |
| `action.sh` | `ksud module action` 异步触发，管理守护进程启停 | WebUI 触发 |
| `apply.sh` | 命令行运行时重新读取配置并生效 | 手动执行 |
| `uninstall.sh` | 卸载时恢复 min_freq 到 270 MHz、杀守护进程 | 模块卸载 |
| `webroot/index.html` | WebUI 图形配置页面 | 管理器里打开 |

### 两种模式

- **`fixed`**（默认）：固定锁频，`FIXED_FREQ` 8 档可选
- **`dynamic`**：守护进程每 `POLL_INTERVAL` 秒轮询背光亮度，
  亮屏 → `SCREEN_ON_FREQ`，息屏 → `SCREEN_OFF_FREQ`

配置持久副本 `/data/adb/gaokun3_gpu_freq.conf`，模块内 `config.conf` 为默认值，
脚本优先读持久副本。WebUI 保存时双写。

### 命令行用法

```bash
# 查看当前状态
adb shell su -c 'sh /data/adb/modules/gaokun3_gpu_freq/apply.sh'

# 切到动态模式
adb shell su -c 'sed -i "s/^MODE=fixed/MODE=dynamic/" /data/adb/modules/gaokun3_gpu_freq/config.conf'
adb shell su -c 'sh /data/adb/modules/gaokun3_gpu_freq/apply.sh'

# 改固定频率（比如 547MHz）
adb shell su -c 'sed -i "s/^FIXED_FREQ=690000000/FIXED_FREQ=547000000/" /data/adb/modules/gaokun3_gpu_freq/config.conf'
adb shell su -c 'sh /data/adb/modules/gaokun3_gpu_freq/apply.sh'
```

### WebUI 配置界面

在 ReSukiSU 管理器里找到本模块，点模块条目上的 WebUI 图标打开图形配置页面：

- 模式切换（固定 / 动态）
- 8 档频率网格选择
- 动态模式参数（亮屏频率、息屏频率、轮询间隔）
- 实时状态（min_freq / cur_freq / 屏幕状态 / 守护进程）
- 点"应用并保存"立即生效

### WebUI 实现踩过的坑

ReSukiSU v4.2.0-rc1 的 `ksu.exec`（走 libsu）行为和 `adb shell` 不同，这一路
踩了多个坑（详见 `CHANGES.md` 第六轮）：

1. `errno` 不可靠 → 不依赖 errno 判断成功
2. heredoc 多行命令不可靠 → 改用逐行 `echo > / >>`
3. 注释里的括号在嵌套引号下报 syntax error → 去掉注释行
4. 后台守护进程继承 stdout pipe 导致 exec 永久挂起 → 改用 `ksud module action` 异步触发
5. stdout 捕获不完整 → writeConfig 不校验直接返回 true
6. `btoa()` 中文抛异常 → 去掉中文注释
7. WebView 缓存旧页面 → 加 cache-busting meta + 版本号
8. readConfig stdout 为空回退默认 fixed → 加 localStorage 缓存兜底

### metamodule 依赖

ReSukiSU v4.2.0-rc1 用 KSU 新版 metamodule 架构。`/data/adb/metamodule/`
为空时 manager 显示"模块未挂载，因为未安装元模块"，WebUI 打开后立刻 finish。

安装 KSU 官方 `meta-overlayfs` v1.3.1（aarch64）后创建 symlink
`/data/adb/metamodule → /data/adb/modules/meta-overlayfs`，重启后 WebUI 正常。

> GPU 模块 `mount: false`（不修改 /system），理论上不需要 metamodule；
> 但这个版本的 manager 在 metamodule 缺失时连 WebUI 也拒绝打开。

### 打包

```bash
cd modules/gaokun3_gpu_freq
zip -X ../../gaokun3_gpu_freq.zip module.prop
zip -X -g ../../gaokun3_gpu_freq.zip config.conf \
    post-fs-data.sh service.sh apply.sh action.sh uninstall.sh \
    webroot/index.html
```

> ⚠️ `module.prop` 必须是 zip 第一个条目（ksud 按顺序解压）。

---

## 7. 排查工具箱

```bash
# ── 显示 / 渲染 ──────────────────────────────────────────
dumpsys SurfaceFlinger | grep -E "activeMode=|renderRate=|Composition efficiency"
dumpsys SurfaceFlinger | grep -E "app duration|SF duration"
dumpsys display | grep -A20 "mVotes"
logcat -s SurfaceFlinger | grep setDesiredMode

# 逐帧耗时（最可靠）
dumpsys gfxinfo <pkg> reset
# ...滚动...
dumpsys gfxinfo <pkg> framestats | grep -A100 -- "---PROFILEDATA---"

# ── GPU ─────────────────────────────────────────────────
cat /sys/class/devfreq/3d00000.gpu/{governor,cur_freq,min_freq,max_freq,trans_stat}
cat /sys/class/devfreq/3d00000.gpu/available_governors

# ── 音频 ────────────────────────────────────────────────
dumpsys media.audio_flinger | grep -A3 "Global session refs"
dumpsys media.audio_policy | grep -A15 "Available output devices"
tinymix | grep -E "WSA|Spkr"
cat /proc/asound/cards; cat /proc/asound/pcm

# ── SELinux ─────────────────────────────────────────────
logcat -d | grep "avc:.*denied" | grep -oE "scontext=u:r:[a-z_]+|tcontext=u:object_r:[a-z_]+|tclass=[a-z_]+" | sort | uniq -c | sort -rn

# ── 日志刷屏 ────────────────────────────────────────────
logcat -d | awk '{print $6}' | sort | uniq -c | sort -rn | head -20
```

---

## 8. 开机后自动旋转需要等较长时间才生效

### 症状

每次重启后，把平板横过来，自动旋转要等一段时间（体感十几秒到几十秒）才响应。

### 结论：这是 SSC 传感器 DSP 的固有沉降时间，不是 bug

根因写在本项目 `gaokun-android/device/huawei/gaokun3/sensors-hal/` 里：

`sensors-gaokun3.rc`：

```
# 传感器 HAL。依赖 hexagonrpcd 先把 SSC 拉起来（它是 class core，先于 hal）。
# ★ 不需要 "required" 之类的强依赖：SscHub 自己会重试等待，
#   而且 hexagonrpcd 起来后 SSC 还要约 20 秒沉降 —— 强依赖也等不到。
```

`SscHub.cpp`：

```cpp
// hexagonrpcd 刚起来时 SSC 约需 20 秒沉降，给足余量（实测 6 秒读不到）。
constexpr int kServiceWaitMs = 60000;
```

启动链：

```
init 起 hexagonrpcd（class core，带 -f /dev/fastrpc-sdsp）
  → hexagonrpcd 拉起 SLPI 上的 SSC（传感器 DSP）
  → SSC 约需 20 秒沉降（固件/registry 初始化，实测 6 秒时还读不到）
  → sensors HAL 的 SscHub 重试 FindSensor("accel"/"gyro")
  → 拿到 accel/gyro 后才开始供数
  → WindowOrientationListener 才有数据可判定方向
```

`SscHub` 的等待策略（`ReaderLoop()`）：前 30 轮每 2 秒查一次（覆盖 60 秒），
之后每 10 秒查一次。这是**必须的**——不是可以缩短的超时。

### 为什么不能「加个 required 强依赖」来加速

`sensors-gaokun3.rc` 的注释已经说明：SSC 沉降发生在 `hexagonrpcd` **起来之后**，
init 的 `required` 只能保证进程启动顺序，等不到沉降完成，加了也没用。

### 为什么不能「重建会话」来加速

`SscHub.cpp` 里有一段明确的警告：

```
⚠️ 千万不要为此重建会话：每次重建都在 SSC 上留下一个被丢弃的客户端，
实测那种 churn 会把传感器枚举彻底弄坏 —— 之后连独立命令行客户端都找不到
accel，必须重启 hexagonrpcd 才恢复。这是 2026-08-20 实测定位到的真实故障。
```

同样，`stage4-findings.md` 也记录了：

> 停/重启 HAL 会污染 SSC 会话，之后连独立客户端都读不到传感器，要重启
> `hexagonrpcd` 才恢复（还得等约 20 秒沉降）。代价是自动旋转当场失效。

### 能做的优化（未实施，可选）

1. **让 `hexagonrpcd` 更早启动**：它现在是 `class core`，已经相当早。若把它
   提到 `on early-init` / `on init` 阶段，可把沉降窗口前移到用户看到锁屏之前。
   风险：fastrpc / remoteproc 依赖可能还没就绪，反而拉长失败重试。
2. **开机后主动触发一次旋转判定**：沉降完成后立刻让
   `WindowOrientationListener` 用当前加速度值算一次方向，而不是等下一次
   `onSensorChanged` 触发阈值。这属于 framework 改动，收益有限。
3. **接受现状**：这只是开机后一次性的等待，之后旋转是即时的（实测
   `mLastFilteredTimestampNanos` 距当前仅 38 ms，`mProposedRotation` 正常）。

### 当前实测状态（健康）

```
mEnabled=true
mCurrentRotation=ROTATION_90
mSensor={SH3001 Accelerometer, Senodia (via Qualcomm SSC), minDelay=20000}
mRate=2
AccelSensorJudge:
  mProposedRotation=1
  mPredictedRotation=1
  mLastFilteredTimestampNanos=... (38.5ms ago)   ← 数据新鲜
  mFlat=false  mSwinging=false  mAccelerating=false  mOverhead=false
  mTiltToleranceConfig=[[-25,70],[-25,65],[-25,60],[-25,65]]
```

传感器在 `dumpsys sensorservice` 里也正常：

```
SH3001 Accelerometer | Senodia (via Qualcomm SSC) | maxRate=50.00Hz | minDelay=20000us
SH3001 Gyroscope     | Senodia (via Qualcomm SSC) | maxRate=50.00Hz
```

框架融合出的 Game Rotation Vector / Gravity / Linear Acceleration 也在。

### 排查命令

```bash
# 1. 传感器 HAL 是否活着
adb shell su -c 'ps -A | grep -E "sensors-service|hexagonrpcd"'

# 2. 传感器是否注册（应有 SH3001 Accelerometer/Gyroscope）
adb shell su -c 'dumpsys sensorservice | head -20'

# 3. 旋转监听器状态
adb shell su -c 'dumpsys window | grep -A14 WindowOrientationListener'

# 4. 数据是否新鲜（mLastFilteredTimestampNanos 应为几十 ms）
adb shell su -c 'dumpsys window | grep -A10 AccelSensorJudge'

# 5. 旋转设置
adb shell su -c 'settings get system accelerometer_rotation'   # 1 = 开启
```

### 如果旋转**永久**失效（不是延迟）

那是另一个已知缺陷：SLPI 崩溃自愈后 SEE 需要 `hexagonrpcd` **再重启一次**才
注册传感器。恢复方法（`stage4-findings.md` #121 §3 实测有效）：

```bash
adb shell su -c 'stop vendor.sensors-gaokun3'
adb shell su -c 'stop vendor.hexagonrpcd-sdsp'
adb shell su -c 'pkill hexagonrpcd'
adb shell su -c 'start vendor.hexagonrpcd-sdsp'
sleep 45
adb shell su -c 'start vendor.sensors-gaokun3'
```

## 9. 已知遗留

- `perf2.IPerf` / `uniperf` HAL 缺失：HyperOS 期望小米性能调度，但 crDroid
  vendor 没有这些二进制。GPU 频率调度已由 `gaokun3_gpu_freq` 模块独立管理
 （8 档可选 + 息屏动态切换），CPU 侧仍靠 `schedutil`。
- `com.android.phone` 开机期 ANR（ExtTelephonyManager 加载问题）。
- DRM 实际为 **8 plane / 3 CRTC**，而 `gaokun-android/docs/hw-inventory.md`
  记录基线是 **25 plane / 6 CRTC**。DTB 不一致。plane 更少时 HWC 能同时
  合成的层数下降，卡顿会更早出现 —— 后续更换 kernel/DTB 时需重新核对。
- `MiuiRefreshRatePolicy` 的 `PRIORITY_APP_REQUEST_RENDER_FRAME_RATE_RANGE`
  投票（`mMinRefreshRate=30, mMaxRefreshRate=60`）来自应用侧
  `Surface.setFrameRate()`。idle timer 修好后不再造成实际掉帧，但该投票
  仍存在。
