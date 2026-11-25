# HyperOS 4 移植通用踩坑记录

本文记录在 `gaokun3`（MateBook E Go，SC8280XP）上把小米 HyperOS 4 / Android 17
移植到 crDroid 17 vendor 时遇到的问题与处理方式。

适用前提：

- 保留 gaokun 的 `boot` / `dtbo` / `vendor_boot` / `vendor` / `odm` / EFI；
- 只替换 `super` 里的 `system` / `system_ext` / `product` / `mi_ext` / `mi_product`；
- donor 与 crDroid 尽量同为 Android 17（SDK 37），跨大版本会触发 VINTF/vendor API 不匹配。

## 1. 不要原地修改 `services.jar` 的 DEX

为了改一个字符串/方法而直接编辑 `services.jar` 里的 `classes*.dex`，会破坏 DEX
字符串表/校验和，`dex2oat` 拒绝整个 jar，表现是卡开机动画或 zygote 反复重启。

需要改框架行为时，优先用 RRO、系统属性、或独立的 framework overlay；不要动
`services.jar` 本体。

## 2. 不要覆盖 `ro.zygote`

crDroid 的 vendor 已经按 gaokun 配好 `ro.zygote=zygote64_32`。在 system prop 里
强制成 `zygote64` 会导致：

```text
RuntimeException: Failed to inform zygote of boot_completed
Caused by: ZygoteStartFailedEx: Error connecting to zygote
```

保留 vendor 的值即可。

## 3. `com.android.phone` 崩溃风暴用“删 APK”解决

modem-less 设备上 `com.android.phone` 可能每秒崩几次：

```text
NoClassDefFoundError: Lcom/qti/extphone/ExtTelephonyManager;
```

`pm disable-user com.android.phone` 对系统包会报
`SecurityException: Cannot disable system packages.`，正确做法是在构建阶段删除
`system/priv-app/TeleService`，而不是运行时禁用。

## 4. drm_hwcomposer 的 `CreateFrameUpdateCommit` 崩溃

现象：

```text
Fatal signal 11 ... android.hardware.composer.hwc3-service.drm
#00 pc ... HwcDisplay::CreateFrameUpdateCommit+0x31c
```

原因是 cached-plan 路径用 `plan[client_z_order]` 索引，client 层数超出时越界。
可在 `composer` APEX 里的 `android.hardware.composer.hwc3-service.drm` 上把
`CreateFrameUpdateCommit` 里的 `cmp w9, #1` 改成跳转到
`CreateLayerToPlaneJoiningPlan()` 重算路径，再用 init/adapt 脚本 bind-mount
覆盖 APEX 内原文件。

注意：

- 补丁位置按 **vendor 的 composer APEX** 定位，换 donor 不影响，但换 vendor/APEX
  版本后 offset 会变，必须重新用反汇编确认，不能照搬固定 offset；
- APEX 是只读的，bind-mount 要放在 `on load-bpf-programs`（或更晚）阶段。

## 5. 静态 overlay：APK 和 `config.xml` 必须一致

`/product/overlay/config/config.xml` 里列出的 static overlay，如果对应 APK 被删除，
zygote 会在初始化时直接 fatal：

```text
java.lang.IllegalStateException: overlay com.miui.systemui.overlay.devices.android
not present in partition /product/overlay in /product/overlay/config/config.xml
```

正确做法是二者保持一致：

- 保留 APK，只从 `config.xml` 删除/禁用对应 `<overlay package="...">`；或
- 同时删除 APK 和 config 条目。

另外，`cmd overlay disable` 对 immutable 的 static overlay 会报
`SecurityException: commit failed`，所以必须在镜像构建阶段处理。

## 6. 指纹：MIUI stub 只看一个 vendor 属性

AOSP 侧 `FingerprintService` / `android.hardware.biometrics.fingerprint` 正常，
`dumpsys fingerprint` 能看到 provider 和 HAL，但 MIUI 仍报：

```text
E FingerprintServiceStubImpl: Fingerprint isHardwareDetected is failed.
```

反编译 `/system_ext/framework/miui-services.jar` 的
`FingerprintServiceStubImpl.isFpHardwareDetected()` 可以看到它只读：

```text
persist.vendor.sys.fp.vendor
```

值非空且不是 `none` 就返回 `true`。因此需要在构建时写入该属性（vendor build.prop
或 init 的 `post-fs-data`），否则 MIUI 会判定“无指纹硬件”。

进一步的限制：

- MIUI 还会尝试 `vendor.xiaomi.hardware.fingerprintextension@1.0::IXiaomiFingerprint`；
  Qualcomm/gaokun vendor 没有这个扩展服务；
- Pad 5 Pro 的 vendor 之所以“指纹定案”，是因为它自带 Goodix HAL/TA 并补了
  `IXiaomiFingerprint` 的 VINTF 声明，这套 vendor 不能直接套到 gaokun；
- 录入界面可以通过 `android.settings.FINGERPRINT_SETUP` 打开，但
  `FINGERPRINT_SETTINGS` 可能因
  `FingerprintSettingsRequireScreenOnToAuthPreferenceController` 为空而 NPE，
  这是 Settings 侧的 controller 问题，不是 HAL。

## 7. 小米互传 / 妙享桌面：缺 `wifi.direct` 特性

现象：

```text
com.xiaomi.mi_connect_service: No service published for: wifip2p
SystemServiceRegistry: ServiceNotFoundException: No service published for: wifip2p
```

`pm list features` 里只有 `android.hardware.wifi`，没有
`android.hardware.wifi.direct`，于是 SystemServer 不启动 `WifiP2pService`，
互传/妙享/Wi-Fi Direct 全部失败。

解决方法：把下面的权限文件放进 `system/etc/permissions/`：

```xml
<permissions>
    <feature name="android.hardware.wifi.direct" />
</permissions>
```

重启后确认：

```text
pm list features | grep wifi.direct
service list | grep wifip2p
```

## 8. 触控 sysfs：批量写参数可能触发复位

在 `post-fs-data` 里一次性写多个触摸 algo 参数，设备可能直接复位到华为 logo。
原因通常是驱动对某个参数的写入/顺序敏感，属于 kernel 侧问题。

建议：

- 启动脚本只做**只读 dump**，把参数写到 `/data/local/tmp/`；
- 需要调参时一次只写一个值，重启验证；
- 不要在开机阶段批量写多个 sysfs 节点。

## 9. 分区大小要按 donor 解压后的体积重算

`super` 里的 logical partition 大小是写死的。换 donor 后如果
`system_ext` 解压后超过原镜像大小，构建会直接在 `cp` 阶段报：

```text
cp: error writing ...: No space left on device
```

需要按 `du -sb` 的解压体积重算 `system/system_ext/product` 的 image 大小，并确保
总和不超过 `super` group 的上限。

另外，liblp metadata 的 partition/extent/group 数量随设备变化，通用解包脚本不要
硬编码 `(8, 52, 4, 24, 3, 48)` 这类 tuple，应按 header 里的 count/size 解析。

## 10. 型号标识可能回退到 vendor

部分 donor 的 `product/etc/build.prop` 里 `ro.product.model=` 是空值。去掉覆盖后，
Android 会回退到 vendor 的 `ro.product.vendor.model`，结果“关于本机”显示成
gaokun/Huawei 而不是 donor 型号。

如果要显示 donor 型号，需要显式写：

```text
ro.product.model
ro.product.brand
ro.product.manufacturer
ro.product.marketname
ro.product.device
ro.product.name
```

## 11. 其它小项

- `ro.miui.has_cust_partition=false`：gaokun 没有 cust 分区，避免 MIUI 反复探测；
- `persist.sys.disable_rescue=true`：避免 rescue party 在调试时反复重启；
- Bluetooth A2DP offload 在 gaokun 上不可用，需关闭：
  `persist.bluetooth.a2dp_offload.disabled=true`；
- 构建脚本输出 `image suspiciously small` 可能只是稀疏/零填充导致的压缩率变化，
  不一定是镜像损坏，应结合 layout/SHA 校验判断；
- 刷机前双清，避免旧的 `/data/property`、overlay 状态影响新系统。

## 12. 验证顺序

1. 能过开机动画进桌面；
2. `logcat -b crash` 无 hwc / phone / system_server 反复崩溃；
3. 120Hz、Wi-Fi、蓝牙、音频正常；
4. `wifi.direct` / `wifip2p` 存在，互传可用；
5. 指纹 HAL 有 provider，`isHardwareDetected` 不再报错；
6. 触控、键盘、笔输入正常。

以上均为在 gaokun3 + crDroid 17 vendor 上实际遇到的问题；不同 donor/vendor 组合
可能需要调整具体 offset、属性名或权限文件。
