# Edge 打不开 —— SELinux untrusted_app ashmem 修复教程

本文记录 HyperOS 4（Pad9 yupei 底包）上 Microsoft Edge 155 点击后闪回桌面的
完整定位过程、根因与修复方法。问题与仓库此前记录的两起 ashmem 事故
（audioserver 无声、相机打不开）同源，都是 `plat_sepolicy.cil` 的域授权遗漏。

---

## 0. 症状与"为什么难查"

点 Edge 图标，启动画面闪一下立刻回到桌面。

难查的地方在于**所有常规排查手段都指向"没崩"**：

| 检查项 | 结果 |
|---|---|
| 崩溃弹窗 | 无 |
| `logcat -b crash` | 空 |
| ANR trace | 无 |
| `/data/tombstones/` | 无对应进程 |
| `am_proc_start` / `am_proc_bound` | 正常 |
| 进程退出码 | `exited cleanly (0)` |

实际时间线（`logcat -b events`）：

```
22:24:49.239 am_proc_start:  [0,17592,10296,com.microsoft.emmx,next-top-activity]
22:24:49.261 Zygote: Process 17592 created for com.microsoft.emmx
22:24:49.265 E ashmem: Unable to open ashmem device: Permission denied
22:24:49.525 E ashmem: Unable to open ashmem device: Permission denied
22:24:49.525 E chromium: HistoryService::Init() failed by way of VisitDelegate::Init failing
22:24:49.549 ActivityManager: Process com.microsoft.emmx (pid 17592) has died: fg TOP
22:24:49.551 Zygote: Process 17592 exited cleanly (0)
```

`am_proc_bound` 到 `am_proc_died` 只隔 **0.2~0.3 秒** —— 死在应用自身代码
刚开始跑的时候，而不是死在任何系统服务调用上。

---

## 1. 定位步骤

### 第一步：确认 Activity 与启动方式

```bash
adb shell cmd package resolve-activity -a android.intent.action.MAIN \
  -c android.intent.category.LAUNCHER com.microsoft.emmx
# → name=com.microsoft.ruby.Main
```

⚠️ 直接 `am start -n com.microsoft.emmx/com.microsoft.ruby.MainRedirectionActivity`
会报 `Activity class does not exist`。Edge 的入口是 `com.microsoft.ruby.Main`。

### 第二步：启动并抓 Edge 进程自身日志

```bash
adb logcat -c
adb shell am start -n com.microsoft.emmx/com.microsoft.ruby.Main
sleep 3
adb logcat -d | grep -iE "emmx|chromium|ashmem"
```

关键输出：

```
E ashmem  : Unable to open ashmem device: Permission denied
E chromium: [ERROR:components/history/core/browser/history_service.cc:2019]
            HistoryService::Init() failed by way of VisitDelegate::Init failing
I Zygote  : Process 17592 exited cleanly (0)
```

`E ashmem: Permission denied` 是 SELinux 的典型信号（DAC 层 `/dev/ashmem*` 是
`crw-rw-rw-`，权限位不可能拒）。

### 第三步：抓 SELinux 拒绝记录

```bash
adb shell su -c 'logcat -d -b all' | grep -i "avc:.*denied" | grep -i ashmem
```

输出：

```
avc: denied { open } for path="/dev/ashmemdec3e404-1674-4200-929e-ac35962058e9"
  scontext=u:r:untrusted_app:s0:c40,c257,c512,c768
  tcontext=u:object_r:ashmem_libcutils_device:s0
  tclass=chr_file permissive=0  app=com.microsoft.emmx
```

**根因确认**：`untrusted_app` 域打开 `/dev/ashmem<uuid>` 被拒 →
`HistoryService::Init()` 失败 → Chromium 主动退出。

### 第四步：查 Edge 的域是怎么来的

```bash
adb shell dumpsys package com.microsoft.emmx | grep -E "versionCode|targetSdk"
# → versionCode=428304805 minSdk=29 targetSdk=37

adb shell su -c 'grep -E "^user=_app" /system/etc/selinux/plat_seapp_contexts | grep untrusted'
```

`seapp_contexts` 的匹配结果：

```
user=_app minTargetSdkVersion=37 domain=untrusted_app type=app_data_file levelFrom=all
user=_app minTargetSdkVersion=34 domain=untrusted_app_34 type=app_data_file levelFrom=all
user=_app minTargetSdkVersion=32 domain=untrusted_app_32 type=app_data_file levelFrom=all
user=_app minTargetSdkVersion=30 domain=untrusted_app_30 type=app_data_file levelFrom=all
user=_app minTargetSdkVersion=29 domain=untrusted_app_29 type=app_data_file levelFrom=all
user=_app minTargetSdkVersion=28 domain=untrusted_app_27 type=app_data_file levelFrom=all
user=_app minTargetSdkVersion=26 domain=untrusted_app_27 type=app_data_file levelFrom=user
user=_app domain=untrusted_app_25 type=app_data_file levelFrom=user
```

Edge 的 `targetSdk=37` 命中第一条，落到**基础域 `untrusted_app`**。

### 第五步：查该域有没有 ashmem 规则

```bash
adb shell su -c 'grep -nE "^\(allow untrusted_app ' \
  /system/etc/selinux/plat_sepolicy.cil'
```

注意这里要用 `untrusted_app` 后面带空格的精确匹配 —— 否则会把
`untrusted_app_25/27/29/30/32/34` 全部匹配进来，误以为规则齐全。

实际结果：**基础域一条 ashmem 规则都没有**。asmem 的 open 只按版本域授予：

```
(allow untrusted_app_34 ashmem_libcutils_device (chr_file (open)))
(allow untrusted_app_32 ...)   (allow untrusted_app_30 ...)
(allow untrusted_app_29 ...)   (allow untrusted_app_27 ...)
(allow untrusted_app_25 ...)
```

而基础域只从 `appdomain` 继承了：

```
(allow appdomain ashmem_device (chr_file (execute)))
(allow appdomain ashmem_libcutils_device (chr_file (execute)))
```

**只有 execute，没有 open**。

---

## 2. 根因链

```
plat_sepolicy.cil 的 ashmem open 只授予 untrusted_app_25/27/29/30/32/34
                        ↓
seapp_contexts 有 minTargetSdkVersion=37 → domain=untrusted_app（基础域）
                        ↓
Edge 155 targetSdk=37 → 落到未授权的基础域
                        ↓
HistoryService::Init() 的 ashmem open 被 SELinux 拒
                        ↓
Chromium 判定为致命错误，主动退出（退出码 0）
                        ↓
现象：图标闪一下立刻回桌面，无崩溃无 ANR
```

同一份 `plat_sepolicy.cil` 的域授权遗漏，这是第三次发作：

| 事故 | 域 | 表现 |
|---|---|---|
| 第二轮 | `audioserver` | 全系统无声、字节系播放器视频区纯黑 |
| 相机 | `hal_camera_default` / `cameraserver` | 相机 App 打开即退出 |
| 本次 | `untrusted_app` | Edge 闪退，无崩溃痕迹 |

---

## 3. 修复

### 不重刷机：KernelSU 模块（即时生效）

模块在仓库根目录 `gaokun3_app_ashmem/`，直接推到设备：

```bash
adb push gaokun3_app_ashmem /data/local/tmp/
adb shell su -c 'rm -rf /data/adb/modules/gaokun3_app_ashmem && \
  cp -r /data/local/tmp/gaokun3_app_ashmem /data/adb/modules/ && \
  chmod -R 755 /data/adb/modules/gaokun3_app_ashmem && \
  chown -R root:root /data/adb/modules/gaokun3_app_ashmem'
adb reboot
```

注入的规则（`post-fs-data.sh` 和 `service.sh` 各一次，后者是双保险）：

```
allow untrusted_app ashmem_libcutils_device chr_file { open read write getattr map ioctl }
allow untrusted_app qemu_hw_prop           file   { read getattr open map }
allow untrusted_app proc_version           file   { read getattr open map }
```

后两条只是消除日志噪音，非致命：

- `qemu_hw_prop` —— Chromium 探测自己是否跑在模拟器（读 `ro.kernel.qemu`）
- `proc_version` —— SentryDeviceInf 线程读 `/proc/version`

### 重刷机：写进 build.py

`scripts/build.py` 的 `policy()` 里已追加同样的规则（CIL 语法），
重新构建后编译进 `precompiled_sepolicy`，不再依赖 KernelSU 模块。

授给**基础域** `untrusted_app` 而不是逐个补 `untrusted_app_35/36/37` 的原因：
以后 targetSdk 38/39/40 的应用，只要 `seapp_contexts` 里没有对应版本域，
就都会落 `untrusted_app`，不会再复现同一个坑。

### 为什么不授 ashmem_device

日志里被拒的 `/dev/ashmem<uuid>` 标签是 `ashmem_libcutils_device`
（见 `plat_file_contexts` 第 59 行）：

```
/dev/ashmem          u:object_r:ashmem_device:s0
/dev/ashmem(.*)?     u:object_r:ashmem_libcutils_device:s0
```

Chromium / Edge 只用 `/dev/ashmem<uuid>` 这个节点（libcutils 的
`ashmem_create_region()` 创建的带 UUID 名字的区域），不碰 `/dev/ashmem` 本体。
按最小权限只授 `ashmem_libcutils_device`。

顺带发现：本机 cil 里那条
`(neverallow base_typeattr_490 ashmem_device (chr_file (open)))` **并不生效**。
`base_typeattr_490` 的 `typeattributeset` 在第 84928 行，neverallow 在第
26469 行 —— neverallow 出现在属性定义之前，编译时该属性还没有类型绑定，
检查不到。实测连 `(allow domain ashmem_device (chr_file (open)))` 都能通过
`secilc -N`。**不能依赖这份 cil 的 neverallow 兜底。**

---

## 4. 验证

### 编译期验证（重刷机路线）

用设备上的 `secilc` 做真实编译，参数与 build.py 一致：

```bash
adb shell su -c 'cp /system/etc/selinux/plat_sepolicy.cil /data/local/tmp/t.cil'
adb shell su -c 'cat >> /data/local/tmp/t.cil <<EOF
(allow untrusted_app ashmem_libcutils_device (chr_file (open read write getattr map ioctl)))
(allow untrusted_app qemu_hw_prop (file (read getattr open map)))
(allow untrusted_app proc_version (file (read getattr open map)))
EOF'
adb shell su -c 'cd /data/local/tmp && secilc -m -M true -G -N -c 33 t.cil \
  /system/etc/selinux/mapping/202504.cil \
  /system_ext/etc/selinux/system_ext_sepolicy.cil \
  /product/etc/selinux/product_sepolicy.cil \
  /vendor/etc/selinux/plat_pub_versioned.cil \
  /vendor/etc/selinux/vendor_sepolicy.cil \
  /system/etc/selinux/plat_sepolicy_genfs_202504.cil \
  -o p -f /dev/null'
# 无输出 = 编译通过
```

### 运行时验证

```bash
# 1. 不再有 ashmem 拒绝
adb shell su -c 'logcat -d | grep -c "avc.*denied.*ashmem"'    # 应为 0

# 2. 不再有 ashmem / HistoryService 错误
adb shell su -c 'logcat -d | grep -E "E ashmem|HistoryService::Init"'   # 应为空

# 3. Edge 进程存活
adb shell pidof com.microsoft.emmx

# 4. 实际界面
adb shell am start -n com.microsoft.emmx/com.microsoft.ruby.Main
adb shell dumpsys activity activities | grep ResumedActivity
# → com.microsoft.emmx/com.microsoft.edge.fre.MicrosoftFirstRunActivity
#   或 com.microsoft.authentication.internal.OneAuthNavigationActivity
```

### 实测结果（重启后）

| 检查项 | 修复前 | 修复后 |
|---|---|---|
| `avc denied ashmem_libcutils_device` | 每次启动 1~3 条 | **0** |
| `E ashmem` / `HistoryService::Init failed` | 每次必现 | **消失** |
| Edge 进程 | bound 后 0.3 s 死亡 | **常驻** |
| Chromium 渲染进程 | 起不来 | 正常 fork |
| 界面 | 闪回桌面 | 进入首次运行向导 / OneAuth 登录页 |

截图确认：Edge 进入 OneAuth 微软账号登录页，输入框激活、虚拟键盘弹出、无报错。

---

## 5. 顺带发现：两个无害的启动噪音

修复后 Edge 日志里还剩两类 WARNING，均为 Chromium 正常行为，**不需要处理**：

```
W chromium: [WARNING:net/cert/ev_root_ca_metadata.cc:118] Not implemented
E chromium: [ERROR:base/android/edge_perf_telemetry_recorder.cc:75]
            EdgePerfTelemetry: ChromeBrowserMainParts_PreMainMessageLoopRun is already ended
```

前者是 EV 根 CA 元数据在 Android 上未实现；后者是 Edge 自己的遥测组件
在主消息循环结束后仍尝试上报，属于 Edge 的已知缺陷。

另外启动初期会看到一串
`avc: denied { find } for name=vendor.qti.hardware.perf2.IPerf/default`
—— 这是 `system_server` 找高通 perf HAL 被拒，与 Edge 无关，是移植遗留，
已在本文范围外。
