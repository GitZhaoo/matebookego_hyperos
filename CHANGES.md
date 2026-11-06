# 修改清单与关键代码

| 文件 / 路径 | 修改 |
|---|---|
| `/system/build.prop`、`/system_ext/etc/build.prop`、`/product/etc/build.prop` | 240 DPI 基准、tablet、ANGLE、skiagl、自然色彩、软件 A2DP、关闭 WFD；具体键值见 [scripts/build.py](scripts/build.py) 的 vals / props |
| `/product/etc/build.prop` | 合并 mi_ext/etc/build.prop 的小米软件身份；保留 yupei |
| `/system/lib{,64}/lib{EGL,GLESv1_CM,GLESv2}_angle.so` | 用 crDroid 同名库替换 |
| `/system/lib64/libutils.so`、`/product/lib64/libutils.so`、`/system/bin/gsid` | 按 AArch64 指令模式，把去除 top-byte tag 后的地址上界改为 56 位；保留其他判断和跳转 |
| `/system/etc/gaokun-apex/*-libutils.so`、`adapt.sh` | 独立修补各 APEX 自己的 libutils；原 SHA 匹配后 bind；本底包涉及 tethering、wifi、media、media.swcodec |
| `/system/etc/init/netbpfload.rc` | bpfloader 前执行 adapt.sh；不 bind / 替换 BPF 目录 |
| `/system/framework/services.jar` 的 classes3.dex | UsbService 检测 `/sys/class/android_usb` 改为 `/sys/class/udc`；主线 USB 初始化后，开发者选项不再因 DeviceManager=null 崩溃 |
| `/system/framework/{arm64,oat/arm64}/services.{odex,vdex,art}`、`services.jar.fsv_meta` | 删除旧预编译缓存 / 元数据；不替换 Settings.apk、framework.jar |
| `/vendor/bin/hw/android.hardware.light-service.gaokun3` | 背光直接读取 color 低字节，兼容 HyperOS 的 8 位灰度值；修复拖动滑块亮度骤黑 |
| `/product/overlay/Gaokun3FrameworkOverlay.apk` | 手动亮度 0.04–1、默认 0.5；关闭 ALS / AOD；矩形显示、120Hz 默认值 |
| `/product/overlay/config/config.xml` | 从原 APK manifest 生成；只列有效 product/overlay 包；immutable 先、mutable 后，设备静态覆盖排最后 |
| `/product/etc/displayconfig/display_id_*.xml`、`display_id_0.xml`、`default.xml` | 1600×2560、240 DPI、完整 0–1 映射；删除整个 HBM 节点；nits 仅为名义值 |
| `/system/etc/init/graphicsengine.rc` | 给小米 Vulkan 缓存预加载服务加 disabled，避免不兼容 mapper 导致 abort |
| `/system/build.prop` | 删除指向不存在文件的 media.settings.xml |
| `/system/etc/sysconfig/gaokun-components.xml` | 单独关闭 FindDeviceStatusManagerProvider |
| `/system/etc/sysconfig/gaokun-powerkeeper.xml` | 单独关闭缺 OEM NTC 数组而崩溃的 ThermalService；保留 Android / vendor 温控 |
| `/vendor/etc/permissions/gaokun3-unavailable-features.xml` | 禁用本机缺少的 ALS、指南针、GPS、电话、NFC 特性 |
| `/vendor/etc/permissions/android.hardware.usb.host.xml` | 声明 USB host |
| `/system_ext/etc/init/gaokun-hyperos.rc` | ADB、WFD 和图形属性启动设置 |
| `/system/etc/init/init.gaokun-bootlog.rc`、`/system/etc/gaokun-bootlog.sh` | 持久启动日志、背光 / display / SurfaceFlinger 快照 |
| `/system/etc/selinux/plat_sepolicy.cil` | 合并 crDroid 权限定义、诊断域、audioserver / untrusted_app 的 ashmem open 和诊断 FD 权限 |
| `/system_ext/etc/selinux/userdebug_plat_sepolicy.cil`（若存在） | 同步 crDroid 权限定义 |
| `/vendor/etc/selinux/precompiled_sepolicy` | Pad9 平台 + crDroid vendor + 202504 mapping 重编译 |
| 三分区 `*_sepolicy_and_mapping.sha256` 及 vendor 对应摘要 | 更新为新策略输入摘要 |
| `/product/app/Updater`、`/system_ext/etc/init/miupdater.rc` | 删除跨机型 OTA / COTA 入口 |

## UI 卡顿 / 视频像 PPT：根因与修复

症状：桌面滑动掉帧、视频播放幻灯片化。实测 `dumpsys SurfaceFlinger` 显示
`Composition efficiency` 0.48、`Total missed frame count` 1724、多个全屏层
`forceClientComposition=true`（回退 GPU client 合成），而应用侧 GPU 渲染本身很快
（gfxinfo GPU 99th = 7ms）。GPU 驱动、turnip、ANGLE、minigbm 均正常。

根因不是 GPU，而是 **SurfaceFlinger 停在 60 Hz 的 display mode 上**：

- 面板有两个 mode：`id=0/hwcId=2 @120Hz`、`id=1/hwcId=3 @60Hz`。
- HyperOS 的 `MiuiRefreshRatePolicy` 以 `PRIORITY_MIUI_REFRESH_RATE` 的
  `RenderVote` 形式给 DisplayModeDirector 投票，读的是 **secure 命名空间**的
  `miui_refresh_rate` / `user_refresh_rate`。AOSP 的 `system.peak_refresh_rate`
  对它无效，所以 `configure_display.py` 只写 system 时 120 Hz 永远不生效。
- 停在 60 Hz 后，DPU 只给 1 个 plane，其余层被 drm_hwcomposer 判为
  `Failed to create DrmKmsPlan`（日志伴随
  `Encountered multiple cursor planes for CRTC 90. Ignoring plane 84`），
  全部回退 client 合成。

修复（`scripts/configure_display.py` 已包含）：

```bash
settings put secure miui_refresh_rate 120
settings put secure user_refresh_rate 120
settings --user 0 put system is_smart_fps 0
settings --user 0 put system peak_refresh_rate 120.0
settings --user 0 put system min_refresh_rate 120.0
settings put global disable_window_blurs 1
settings put secure disable_window_blurs 1
settings put global support_dynamic_island_blur 0
settings put secure miui_home_recents_blur_mode 0
setprop ctl.restart surfaceflinger   # 必须；否则当前 session 仍留在 60 Hz
```

修复后实测（重启设备后仍保持）：`activeMode hwcId=2 @120Hz`、
`Composition efficiency` 0.98–1.0、`Total missed frame count` 2、
CLIENT 层 0 / DEVICE 层 7、`Failed to create DrmKmsPlan` 0 次、
设置列表滚动 532 帧仅 3 帧 jank（0.56%）。

注：`screenrecord` 报 `unable to create video/avc codec instance` 属预期 ——
硬件编码按设计关闭（见上文）。视频**解码**正常，`c2.v4l2.avc/hevc/vp9.decoder`
均在册；小米「媒体查看器」实际用内置 VLC 软解，播放 1080p60 时 CPU 占用接近 0。

另：本机 DRM 实际为 8 plane / 3 CRTC，而 `gaokun-android/docs/hw-inventory.md`
记录基线为 25 plane / 6 CRTC。若后续更换 kernel/DTB，需重新核对 plane 数量 ——
plane 更少时 HWC 能同时合成的层数会下降，卡顿会更早出现。

## 第二轮：应用内卡顿、红果短剧黑屏、无声音 —— SELinux audioserver ashmem

现象：桌面/设置已流畅（120Hz + 硬件合成修复后），但应用内滑动仍卡；红果短剧
进入播放页后视频区纯黑；系统完全无声。

排查结论（三个现象同源）：

1. **无声 + 红果黑屏的根因**：`plat_sepolicy.cil` 只给了 `appdomain`
   `ashmem_libcutils_device (chr_file (execute))`，`audioserver` 域一条 ashmem
   规则都没有。Enforcing 下 AudioFlinger `createTrack_l()` 分配 AudioTrack
   控制块（ashmem）被拒 → 返回 -12（"no control block?"）→ 全系统无声。
   字节系播放器（红果短剧 libttmplayer）以音频为主时钟：音轨建不出 → 不开始
   解码 → 界面正常、视频区黑屏。实测修复前 AudioTrack 失败 47 次/秒（死循环重试）。
2. **应用内滑动卡**：GPU devfreq 只有 `simple_ondemand`（PERFORMANCE/USERSPACE
   governor 编成 =m 但设备上没有 .ko），1600×2560@120Hz 滑动负载下 GPU 只在
   270/547MHz 间跳。`min_freq=690` 后 gfxinfo 90th 13ms→5ms、missed vsync 3→0。
3. **扬声器**：`audioroute` 开机 oneshot 正常执行；没声音纯粹因为没有音频流
   （第 1 条）。SoundWire "Bus clash/Alert" 刷屏在 crDroid 基线上同样存在，
   实测不影响出声。⚠️ 反复 `killall audioserver` + 强制 unbind
   `qcom-soundwire`/`snd-sc8280xp` 会导致 SoundWire port 泄漏
   （`All ports busy`, EBUSY），只能重启恢复 —— 不要再这么做。

修复：

- KernelSU 模块 `gaokun3_audio_fix`（`sepolicy.rule` + `service.sh`）：
  运行时注入 audioserver 的 ashmem/prop 规则；开机把 GPU `min_freq` 钉在
  690MHz、扬声器 PA 与系统音量置 0（用户要求静音）。
- `scripts/build.py` policy()：`plat_sepolicy.cil` 补 `(allow audioserver
  ashmem_libcutils_device/ashmem_device ...)` 与两个 prop 读取规则，下次
  构建生效后模块的 sepolicy 部分即可退役。
- 麦克风硬件本身正常（tinycap 3 秒录到非静音波形，DMIC0+1 由 audioroute
  路由），录音应用链路随 ashmem 修复打通。

## 第三轮：SurfaceFlinger 空闲降频到 20 Hz（应用内卡顿的真正主因）

现象：GPU 已锁 690 MHz、合成效率已正常，但 ReSukiSU、哔哩哔哩等应用滑动
仍明显卡顿；哔哩哔哩甚至触发 ANR（`Input dispatching timed out ... Waited
10000ms for MotionEvent(action=DOWN)`）。

定位（两条独立证据指向同一处）：

1. `dumpsys gfxinfo <app> framestats` 逐帧解析：**120 帧的 `FrameInterval`
   全部是 50.00 ms**（p50=p90=p99=50.00ms），即 20 fps，且与
   `presDeadline 50000046 ns` 完全对应。`DequeueBufferDuration` p50 只有
   0.02ms —— 取缓冲不是瓶颈。
2. `dumpsys SurfaceFlinger` 连续采样：滑动时 `renderRate` 在
   **120 → 20 → 120** 之间反复横跳，每次触摸升到 120、松手立刻掉回 20。
   `logcat -s SurfaceFlinger` 的 `setDesiredMode` 同样显示
   `fps=120.00 Hz` 与 `fps=20.00 Hz` 秒级交替。
3. ANR trace（`/data/anr/anr_2026-10-24_10-53-14-890`）显示 B站主线程阻塞在
   `ThreadedRenderer.syncAndDrawFrame` 的 `pthread_cond_wait`，RenderThread
   停在 `rx::vk::CommandQueue::submitCommands`（ANGLE→Vulkan→turnip）——
   这是**结果**：帧被 20 Hz 节流后，主线程一直在等 RenderThread。

根因是 SurfaceFlinger 的空闲降频（idle timer）：无触摸时把 renderRate 压到
20 Hz，而恢复不够快，导致滑动全程都在 20 Hz 上跑。`MiuiRefreshRatePolicy`
的 `PRIORITY_MIUI_REFRESH_RATE` 投票上限已是 120，`min_refresh_rate=120`
也已写入，但都**管不到 idle timer**。

修复（KernelSU 模块 `gaokun3_audio_fix`）：

```
setprop debug.sf.set_idle_timer_ms 1000000
setprop debug.sf.set_touch_timer_ms 1000000
setprop debug.sf.enable_frame_rate_override false
```

⚠️ 这三个属性由 SurfaceFlinger **启动时读取**，必须在 SF 起来之前设置，所以放在
模块的 `post-fs-data.sh`（`service.sh` 里再设一次作为兜底）。只 setprop 然后
`ctl.restart surfaceflinger` 也能立刻生效，但重启后会丢。

修复后实测（Settings 列表滚动）：

| 指标 | 修复前 | 修复后 |
|---|---:|---:|
| 90th 百分位 | 13 ms | **7 ms** |
| 95th | 24 ms | **8 ms** |
| 99th | 85 ms | **21 ms** |
| Missed Vsync | 27 | **0** |
| Janky | 17.25% (legacy) | **0.72%** |

`renderRate` 连续 14 次采样（滚动中）全部 120.00 Hz，静止 20 秒后仍为
120.00 Hz。

⚠️ 附带发现（未修，影响小）：小米 `AmlWifiScoreReportInjector` 每次 Wi-Fi
打分都调 `TelephonyManager.isDataEnabled()`，本机无 telephony 服务，
`IllegalStateException: telephony service is null` 每次抛完整堆栈，
实测约 1.2 次/秒。量不大，暂不处理；若要消除可考虑禁用该 scorer。

## KernelSU 模块打包注意

`ksud module install` 按 zip 条目顺序解压，**`module.prop` 必须是压缩包里的
第一个条目**，否则它解压完 `module.prop` 就停止，其余文件不会落地（表现为
模块目录里只有 `module.prop`，脚本缺失）。正确做法：

```bash
zip -X out.zip module.prop
zip -X -g out.zip sepolicy.rule service.sh post-fs-data.sh
```

覆盖安装同样不可靠（旧文件会被保留、新文件可能丢失）；改动模块内容时先
`rm -rf /data/adb/modules/<id> /data/adb/modules_update/<id>` 再装。

## 第四轮：日志刷屏与两个"被高估"的问题

上一轮修完 idle timer 后设置页滚动已是 90th 6–7 ms、Missed Vsync 0，但
ReSukiSU / 哔哩哔哩仍有体感卡顿。逐个核对了当时怀疑过的几项，结论如下。

**已修：drm_hwcomposer 日志刷屏**

`drmhwc` 每个 validate 周期都打
`Encountered multiple cursor planes for CRTC 90. Ignoring plane 84`。
实测 **30 秒 2230 行（74 行/秒）**，而同一时间 `Failed to create DrmKmsPlan`
计数是 **0** —— 重复的 cursor plane 被跳过，合成本身完全正常，纯属噪音。

修法：`setprop log.tag.drmhwc E`（标准 Android log 级别控制）。
效果：drmhwc 输出 10 秒内 0 行；系统总日志量从 **15257 → 6091 行/30 秒（-60%）**。

**未修，且经核实影响很小：TelephonyManager 异常**

```
E TelephonyManager: java.lang.IllegalStateException: telephony service is null.
  at AmlWifiScoreReportInjector.isMobileDataDisabled()
```
小米 Wi-Fi 评分器每次打分都调 `TelephonyManager.isDataEnabled()`，本机无
modem。实测 **9 次 / 30 秒**，远低于 drmhwc 的 2230 行，不是卡顿主因，暂不处理。

**未修，且不是卡顿主因：ANGLE `submitCommands`**

B站 ANR trace 里 RenderThread 停在
`rx::vk::CommandQueue::submitCommands`，一度怀疑是 GPU 提交队列阻塞。
复核后判定这是**结果而非原因**：帧被 idle timer 节流到 20 fps 后，主线程在
`ThreadedRenderer.syncAndDrawFrame` 等 RenderThread，RenderThread 又在等
Vulkan 队列排空。idle timer 修好后该栈不再出现。

补充：本机 vendor 分区**没有原生 GLES 驱动**（`/vendor/lib64/egl/` 不存在），
渲染只有 ANGLE→Vulkan→turnip 一条路，没有回退可选，这也是为什么
`persist.graphics.egl=angle` 是唯一可行配置。

**未修：`app duration` 与 `SF duration` 不匹配**

`dumpsys SurfaceFlinger` 显示 `app duration 15666682 ns`（63.8 Hz）而
`SF duration 7333341 ns`（136 Hz）。试过
`debug.sf.early.app.duration` 等属性，**无效** —— 该值由已激活的 display
mode 推导，不由 prop 控制。`renderRate` 已是 120 Hz，属调度估算值偏差，
不影响实际出帧。

**另一处启动期噪音（一次性，已自愈）**

12:50 有一批 `com.android.phone` ANR
（`failed to complete startup`，`/data/anr/anr_2026-10-24_12-50-36-*`），
开机后 `com.qti.phone` 正常驻留，之后未复发。与 README 记录的
ExtTelephonyManager 加载问题同源，属已知遗留。

## 当前模块 `gaokun3_audio_fix` 完整内容

| 文件 | 作用 |
|---|---|
| `module.prop` | 中文名称与说明 |
| `sepolicy.rule` | audioserver 的 ashmem / prop 访问权限 |
| `post-fs-data.sh` | SF 启动前：idle timer、frame-rate override、`log.tag.drmhwc` |
| `service.sh` | 运行时：GPU min_freq 690 MHz（不再改音量） |

重启后实测：`renderRate=120.00 Hz`、`GPU min_freq=690000000`、
`log.tag.drmhwc=E`、`debug.sf.set_idle_timer_ms=1000000`、
`getenforce=Enforcing`、drmhwc 日志 0 行/10 秒。

### 关于扬声器音量（已撤回开机静音）

早期版本的 `service.sh` 会在每次开机把 `STREAM_MUSIC` 设为 0（当时按用户
要求做静音验证）。该行为已**移除**：现在不碰音量，开机沿用用户上次的设定。

需要注意两处音量的分工：

- `settings system volume_music_speaker` / AudioService 音量：用户可见的
  音量滑块，模块不再改写。
- `SpkrLeft/Right PA Volume`（硬件增益）：由系统自带的
  `audioroute.sh` 在 `sys.boot_completed=1` 时写为 21（= +6 dB，正常值）。
  模块不再覆盖它 —— 早先模块写 0 其实会被 audioroute 后执行覆盖掉，等于
  没生效，反而容易误导。

验证：重启后 `volume_music_speaker=8`、`AudioService volume is 8`、
`PA Left=21`，即音量按用户设定保持，扬声器可正常出声。

## 重新刷机时的行为（重要）

所有软件侧修复都已写进本仓库，**重新构建并刷入 super 后，不再需要 KernelSU
模块**。对应关系：

| 修复 | 落地位置 | 刷机后是否自动生效 |
|---|---|---|
| audioserver ashmem / prop 权限 | `scripts/build.py` `policy()` 追加到 `plat_sepolicy.cil` | ✅ 编译进 `precompiled_sepolicy` |
| untrusted_app 基础域 ashmem open（Edge 等 targetSdk≥35 应用） | 同上，`policy()` 追加 | ✅ 编译进 `precompiled_sepolicy` |
| SF idle timer / frame-rate override / `log.tag.drmhwc` | `scripts/build.py` 写入 `system_ext/etc/init/gaokun-hyperos.rc` 的 `on post-fs-data` | ✅ |
| GPU `min_freq=690MHz` | 同上，`on property:sys.boot_completed=1` | ✅ |
| 刷新率（secure 命名空间） | 同上的 `exec` 调 `system/etc/gaokun-refresh.sh` | ✅ |
| 显示密度 320 / 字号 1.25 | 同上的 `system/etc/gaokun-refresh.sh`（`wm density 320` + `font_scale 1.25`） | ✅ |
| 刷新率（首次配置） | `scripts/configure_display.py` | ⚠️ 需手动跑一次（写 userdata） |
| `config_defaultRefreshRate=120` | `assets/overlay/res/values/config.xml` | ✅ 编进 RRO |

`gaokun-refresh.sh` 之所以单独成文件、由 `exec` 拉起，是因为 `settings` 是
binder 调用，init 自身域没有权限；用 `sh` 起来后落到 `gaokun_bootdiag`
（项目已有的 `typepermissive` 域）就能写。

⚠️ 需要手工做的是 `configure_display.py` 里的**亮度与色彩模式**（写 userdata）。
密度 320 / 字号 1.25 也已写进 `gaokun-refresh.sh`，开机自动重放，不再依赖手动。

密度必须用 `wm density` 而不是 `settings put secure display_density_forced`：
实测后者只改设置项、不改变生效值 —— `dumpsys window` 的 `mForcedDensity` 和
`dumpsys display` 的 `logical density` 都停在旧值，只有 `wm density` 会同时写
设置并让 WindowManager 重新应用。

`build.prop` 的 `ro.sf.lcd_density` / `persist.miui.density_v2` 保持 240 不动
（系统 / MIUI 的共同基准），320 仅是用户显示大小覆盖。

注意密度对桌面图标无效：HyperOS 4 桌面是 Flutter 应用（`libapp_launcher.so` 16MB
+ `libapp.so` 29MB，APK 内无 dex），按固定的逻辑宽度 1534 排布，
`wm density` 在 240/288/320/400 下图标实测都是 78px 不变。该项只放大设置等
系统 UI。桌面图标尺寸是 Dart 层的固定值（`IconConfig.iconSize = 48.66`），
不读 density、不读 SharedPreferences、也不受网格列数影响。

KernelSU 模块 `gaokun3_audio_fix` 现在只作为**当前这台机器**的临时手段
（不重新刷机时用它生效）。重新刷入含上述改动的 super 后可以删掉。

关键修复原理：

```smali
# Pad9 services.jar / classes3.dex / com/android/server/usb/UsbService
# 原 const-string 指令寄存器不变，只改字符串：
"/sys/class/android_usb"  ->  "/sys/class/udc"
```

```cpp
// gaokun lights 对 BACKLIGHT 的源码等价修改：
// 原：亮度 = RGB Rec.601 加权值
// 新：亮度 = state.color & 0xff
// 保留后续 brightness * max_brightness / 255 缩放。
```

本目录针对已验证的 lights 二进制执行 4 字节补丁：SHA-256 `d549cd52be089d11cda45d69f723cd3bf88637631261ca0de82398a17dfd4d45`，文件偏移 `0x370a0`，指令 `0x53087d08` → `0x39400048`（`ldrb w8,[x2]`）。版本不同则按 [Lights.cpp 源码](https://github.com/vahiru/gaokun-android/blob/main/device/huawei/gaokun3/lights/Lights.cpp) 修改并重新构建，不套用这个偏移。

OS4 的 NetBpfLoad 会检查 BPF 文件的 st_dev；从 system 绑定整个 BPF 目录会导致启动失败。本底包缺 CONFIG_XDP_SOCKETS 时 osrtpPolicy.o 可出现 EINVAL，但实机 loader 最终成功退出；不得沿用 OS3 的目录绑定方案。

## 第五轮：Edge 打不开 —— untrusted_app 基础域缺 ashmem open

### 症状

点 Edge 图标 → 闪现启动画面 → 立刻回桌面。**没有崩溃弹窗、没有 ANR**，
`logcat -b crash` 是空的，`/data/tombstones/` 里也找不到对应进程 ——
进程是"干净退出"的：

```
E ashmem  : Unable to open ashmem device: Permission denied
E chromium: [ERROR:components/history/core/browser/history_service.cc:2019]
            HistoryService::Init() failed by way of VisitDelegate::Init failing
I Zygote  : Process 17592 exited cleanly (0)
```

`am_proc_bound` 之后 0.2~0.3 秒就 `am_proc_died`，Activity 被 WMS 标记为
`dead AR ... isExiting` 然后移除。这一串表现最容易把排查方向带到
"Edge 自身问题"或"HyperOS 兼容性"上去。

### 根因

SELinux 拒绝：

```
avc: denied { open } for path="/dev/ashmemdec3e404-1674-4200-929e-ac35962058e9"
  scontext=u:r:untrusted_app:s0:c40,c257,c512,c768
  tcontext=u:object_r:ashmem_libcutils_device:s0
  tclass=chr_file permissive=0  app=com.microsoft.emmx
```

`plat_sepolicy.cil` 里 ashmem 的 open 是按 targetSdk 拆域授予的，最高只到
`untrusted_app_34`：

```
(allow untrusted_app_34 ashmem_libcutils_device (chr_file (open)))
(allow untrusted_app_32 ...)
(allow untrusted_app_30 ...)
(allow untrusted_app_29 ...)
(allow untrusted_app_27 ...)
(allow untrusted_app_25 ...)
```

而 `plat_seapp_contexts` 里有：

```
user=_app minTargetSdkVersion=37 domain=untrusted_app type=app_data_file levelFrom=all
```

Edge 155 的 `targetSdk=37`，匹配不到任何 `untrusted_app_3x` 版本域，于是落到
**基础域 `untrusted_app`** —— 这个域在整份策略里一条 ashmem 规则都没有
（只有 `(allow appdomain ashmem_device (chr_file (execute)))` 和
`(allow appdomain ashmem_libcutils_device (chr_file (execute)))` 这种 execute
权限，没有 open）。`HistoryService::Init()` 的 ashmem open 被拒后
Chromium 判定为致命错误，主动退出。

这是同一份 `plat_sepolicy.cil` 授权遗漏的第三次发作，前两次分别是
audioserver 域（第二轮，全系统无声）和 hal_camera_default / cameraserver 域
（相机打不开）。

### 修复

`scripts/build.py` 的 `policy()` 追加：

```cil
(allow untrusted_app ashmem_libcutils_device (chr_file (open read write getattr map ioctl)))
(allow untrusted_app qemu_hw_prop (file (read getattr open map)))
(allow untrusted_app proc_version (file (read getattr open map)))
```

授给基础域而不是逐个补 `untrusted_app_35/36/37`：以后 targetSdk 38/39/40
的应用只要 `seapp_contexts` 里没有对应版本域，就都落 `untrusted_app`，
不会再复现同一个坑。

后两条只是消除 Chromium 启动时的日志噪音，非致命：
`qemu_hw_prop` 是 Chromium 探测自己是否跑在模拟器（读 `ro.kernel.qemu`），
`proc_version` 是 SentryDeviceInf 线程读 `/proc/version`。

### 关于 ashmem_device：本机 neverallow 拦不住东西

最初也加了 `(allow untrusted_app ashmem_device (chr_file (open ...)))`，
后来按最小权限撤掉了。顺带发现本机 cil 里那条
`(neverallow base_typeattr_490 ashmem_device (chr_file (open)))` **实际不生效**：

`base_typeattr_490` 的 `typeattributeset` 定义在第 84928 行，而 neverallow
在第 26469 行 —— neverallow 出现在属性定义**之前**，CIL 编译时该属性还没有
类型绑定，检查不到。实测连 `(allow domain ashmem_device (chr_file (open)))`
这种明显违规的语句都能通过 `secilc -N`。

结论：不能依赖这份 cil 的 neverallow 兜底，权限收紧只能靠人工判断。
日志里被拒的 `/dev/ashmem<uuid>` 标签就是 `ashmem_libcutils_device`
（`plat_file_contexts:59`），Chromium 只用这个节点，所以不需要 `ashmem_device`。

### 验证

用设备上的 `secilc` 做真实编译验证（`-m -M true -G -N -c 33`，与 build.py
一致），追加规则后的完整策略集编译干净通过。运行时验证：

| 检查项 | 修复前 | 修复后 |
|---|---|---|
| `avc denied ashmem_libcutils_device` | 每次启动 1~3 条 | **0** |
| `E ashmem` / `HistoryService::Init failed` | 每次启动必现 | **消失** |
| Edge 进程存活 | bound 后 0.3 s 死亡 | **常驻** |
| Chromium 渲染进程 | 起不来 | 正常 fork |
| 实际界面 | 闪回桌面 | 进入首次运行向导 |

重启后 Edge 能正常走到 `com.microsoft.authentication.internal.OneAuthNavigationActivity`
（OneAuth 微软账号登录页），截图确认输入框激活、键盘弹出、无报错。

### KernelSU 模块 `gaokun3_app_ashmem`

不重刷机时的临时手段，`post-fs-data.sh` + `service.sh` 两处用
`ksud sepolicy patch` 注入同样的 3 条规则。`service.sh` 是双保险 ——
`ksud sepolicy patch` 是运行时注入，某些启动时序下 post-fs-data 阶段的注入
可能被后续策略重载覆盖。

模块装到 `/data/adb/modules/gaokun3_app_ashmem` 后重启实测生效。


## 源码对应

- 分区复制、身份 / 属性、ANGLE、USB DEX、APEX、lights、策略重编译：[scripts/build.py](scripts/build.py)。
- RRO 编译与有效覆盖排序：[scripts/overlay.py](scripts/overlay.py)，输入 [AndroidManifest.xml](assets/overlay/AndroidManifest.xml)、[config.xml](assets/overlay/res/values/config.xml)。
- 地址上界指令识别：[patch_xiaomi_va_os4.py](scripts/patch_xiaomi_va_os4.py)；只匹配可执行段内的已知模式。
- 显示配置：[assets/display.xml](assets/display.xml)；完整删除 HBM 节点，不能只留 enabled=false 的空节点。
- 日志：[assets/bootlog.rc](assets/bootlog.rc)、[assets/bootlog.sh](assets/bootlog.sh)。
- super 元数据校验与封装：[scripts/pack_super.py](scripts/pack_super.py)。
- 主机二进制导出：[scripts/capture_base.py](scripts/capture_base.py)；USB Linux 刷写：[scripts/flash.py](scripts/flash.py)；离线日志：[scripts/collect_logs.py](scripts/collect_logs.py)。
- 首次显示设置：[scripts/configure_display.py](scripts/configure_display.py)；这部分写入 userdata 的 Settings / WM 配置，不是镜像内默认值。

镜像内绝对路径中的 `/system` 在 system-as-root 镜像中对应 `system/` 子目录。工作区 `assets/` 与 Android 路径不同；目标位置由 build.py 指定。新增文件显式写入 UID/GID、mode 和 SELinux 标签，复用文件保留原 inode 属性。


## 第六轮：GPU 频率调度拆分独立模块 + WebUI 配置界面

### 背景

`gaokun3_audio_fix` 模块此前同时承担三件事：audioserver ashmem sepolicy
注入、SurfaceFlinger idle timer 修复、GPU `min_freq` 锁 690 MHz。GPU 锁频
是权宜之计（在 SF idle timer 修复前打的补丁），且用户希望：

1. GPU 频率调度从 audio_fix 拆分出来，独立成一个 KSU 模块；
2. 支持 8 档频率选择（270 / 410 / 500 / 547 / 606 / 640 / 655 / 690 MHz）；
3. 支持 fixed（固定锁频）和 dynamic（息屏降频 / 亮屏高频）两种模式；
4. 在 ReSukiSU 管理器里提供 WebUI 图形配置页面，不用敲命令。

### GPU 现状（sc8280xp，Adreno）

- devfreq 节点：`/sys/class/devfreq/3d00000.gpu`
- governor：只有 `simple_ondemand`（`performance`/`userspace` 编成 `=m` 但
  设备上无 `.ko`；`msm-adreno-tz` 是闭源 vendor 代码，主线没有）
- 8 档频率：270 / 410 / 500 / 547 / 606 / 640 / 655 / 690 MHz
- `simple_ondemand` 的 50ms 轮询在 1600×2560@120Hz UI 滑动负载下升频不积极，
  GPU 只在 270/547 MHz 间跳。实测 gfxinfo（Settings 列表滚动）：
  `min_freq=270` → 90th 13ms、missed vsync 3；
  `min_freq=690` → 90th 5–6ms、missed vsync 0。
- 息屏检测节点：`/sys/class/backlight/ae96000.dsi.0/brightness`
  （灭屏=0，亮屏>0；`bl_power` 在本驱动不更新，不可用）

### 新模块 `gaokun3_gpu_freq`

路径：`modules/gaokun3_gpu_freq/`，从 `gaokun3_audio_fix` 拆分而来。

| 文件 | 作用 | 执行时机 |
|---|---|---|
| `module.prop` | 模块元信息 | — |
| `config.conf` | 默认配置（模式 + 频率 + 轮询间隔） | 被脚本读取 |
| `post-fs-data.sh` | SF 启动前早期应用 min_freq | post-fs-data |
| `service.sh` | fixed 写入 / dynamic 起守护进程 | boot_completed |
| `action.sh` | 由 `ksud module action` 异步触发，管理守护进程启停 | WebUI 触发 |
| `apply.sh` | 命令行运行时重新读取配置并生效 | 手动执行 |
| `uninstall.sh` | 卸载时恢复 min_freq 到 270 MHz、杀守护进程 | 模块卸载 |
| `webroot/index.html` | WebUI 图形配置页面 | 管理器里打开 |

**两种模式**（`config.conf` 里 `MODE=`）：

- `fixed`（默认）：固定锁频，`FIXED_FREQ` 8 档可选
- `dynamic`：守护进程每 `POLL_INTERVAL` 秒轮询背光亮度，
  亮屏 → `SCREEN_ON_FREQ`，息屏 → `SCREEN_OFF_FREQ`

配置持久副本 `/data/adb/gaokun3_gpu_freq.conf`，模块内 `config.conf` 为默认值，
脚本优先读持久副本。WebUI 保存时双写。

### `gaokun3_audio_fix` 同步调整

- `service.sh` 移除 `echo 690000000 > min_freq`，只保留 SF idle timer / drmhwc
  日志设置
- `module.prop` 更新描述（v1.2），注明 GPU 已拆分
- `README.md` 更新，指向新 GPU 模块

### WebUI 实现踩过的坑（重要）

ReSukiSU v4.2.0-rc1 的 `ksud` 支持 WebUI（`webroot/index.html` +
`kernelsu` JS API），manager 含 `WebUIActivity` + `kernelsu://webui/` scheme。
WebUI 通过 `window.ksu.exec(cmd)` 以 root 执行 shell 命令。这一路踩了多个坑：

1. **`errno` 不可靠**：`ksu.exec` 返回的 `errno` 字段在这个版本不可靠
   （同步 API 下可能 undefined 或始终非 0），用 `r.errno === 0` 判断成功会
   误报失败。改用 stdout 标记或读回校验，最后简化成不校验直接成功。

2. **heredoc 多行命令**：`cat > file <<'EOF'...EOF` 在 `ksu.exec` 里不可靠。
   改用逐行 `echo > / >>` 写入。

3. **括号语法错误**：注释行 `# ...(WebUI)` 在 `echo '...'` 里，经
   `su -c '整条命令'` 嵌套引号传递时，括号被当成子 shell 语法，报
   `syntax error: unexpected '('`。去掉注释行、配置值不用引号（纯字母数字）。

4. **守护进程阻塞 exec**：dynamic 模式 `gpu_freq_daemon &` 后台进程继承
   exec 的 stdout pipe，pipe 不关闭导致 `ksu.exec` 永久挂起（"卡在应用中"）。
   改用 `ksud module action` 异步触发 `action.sh` 管理守护进程，WebUI 不等待。

5. **stdout 捕获不完整**：`ksu.exec` 的 stdout 捕获机制对含管道/重定向的
   命令不可靠，`echo WROTE_OK` 的输出可能不被捕获。最终方案：writeConfig
   不依赖 stdout，逐行 echo 写入后直接 `return true`，配置校验交给 refresh。

6. **btoa 中文异常**：配置含中文注释时 `btoa()` 抛 `InvalidCharacterError`，
   使 Promise reject、按钮永久卡在"应用中"。去掉中文注释。

7. **WebView 缓存**：更新 index.html 后 WebView 可能加载缓存的旧页面。
   加 `<meta http-equiv="Cache-Control" content="no-cache...">` 和版本号标识。

8. **readConfig 回退默认值**：`readConfig` 用 `ksu.exec` 的 stdout 读配置，
   stdout 为空时回退默认 `fixed`，导致重进 WebUI 显示错误模式。加 localStorage
   缓存兜底，writeConfig 成功后同步更新缓存。

### metamodule 安装

ReSukiSU v4.2.0-rc1 用 KSU 新版 metamodule 架构。`/data/adb/metamodule/`
为空时 manager 显示"模块未挂载，因为未安装元模块"，WebUI 打开后立刻 finish
（无崩溃日志，onCreate 后主动 finish）。

安装 KSU 官方 `meta-overlayfs` v1.3.1（`meta-overlayfs-aarch64` 二进制）：
`ksud module install` 后创建 symlink
`/data/adb/metamodule → /data/adb/modules/meta-overlayfs`，并建 2GB ext4
image 用于模块存储。重启后 metamodule 生效，WebUI 正常打开。

> 注：GPU 模块 `mount: false`（不修改 /system），理论上不需要 metamodule
> 就能工作；但这个版本的 manager 在 metamodule 缺失时连 WebUI 也会拒绝打开。

### 最终状态

- GPU 模块独立，WebUI 可在管理器里图形化配置模式 + 频率
- 配置和 WebUI 页面重启后保持（`modules/` 持久，`modules_update/` 为空）
- metamodule 已安装，模块挂载正常
- audio_fix 只管音频 sepolicy + SF idle timer，不再碰 GPU
