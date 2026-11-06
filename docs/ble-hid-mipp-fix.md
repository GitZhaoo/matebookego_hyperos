# BLE HID 外设（鼠标/键盘）配对后无响应 —— 根因与修复

> 适用机型：MateBook E Go（gaokun3）运行移植版 HyperOS 4
> 症状：蓝牙鼠标（如 Logitech M585/M590）能配对成功，但完全无响应，设置里也搜不到某些热点/设备
> 修复脚本：`scripts/fix_ble_hid_mipp.py`

## 症状

- 蓝牙鼠标配对成功，显示"已连接"，但光标不动
- `dumpsys bluetooth_manager` 里：
  ```
  Profile: HidHostService
    mInputDevices:
   XX:XX:XX:XX:95:2E : Selected transport=2 HID connection state=0 HOGP connection state=0
  ```
  `HID connection state = 0` / `HOGP connection state = 0`，即 HID 通道从未建立
- `/proc/bus/input/devices` 里没有对应的输入设备节点
- logcat 关键错误：
  ```
  bta_hh_co.cc:1007  bta_hh_co_open: failed to open /dev/mipp_pen0, try to get itouchfeature service
  bta_hh_co.cc:1020  bta_hh_co_open: [CON-TF-BT]failed to get touchfeature service
  btif_hh.cc:744     hh_open_handler: Failed to open uhid driver
  HidHostService     broadcastConnectionState: prevState=1 -> newState=0
  gatt_main.cc:376   GATT fixed channel is no longer useful, start link idle timer for 1 seconds
  ```

## 根因

移植版把机型伪装成 `yupei`（小米 Pad 9），小米定制蓝牙栈
（`packages/modules/MiuiBluetooth/system/btif/co/bta_hh_co.cc`）因此判定本机
"支持妙享笔（MIPP）"，于是**所有 HOGP(BLE) HID 设备都被强制走 MIPP 私有路径**：

```
bta_hh_co_open()
  -> check_mipp_device() == true
  -> open("/dev/mipp_pen0")        # 华为硬件上没有这个节点
  -> getTouchFeature()             # vendor.xiaomi.hw.touchfeature 服务不存在
  -> 整体失败，返回 0              # 注意：没有 fallback 到标准路径
  -> "Failed to open uhid driver"
  -> HID 通道没建立 -> GATT 对 HID 无用 -> 1 秒后 ACL 被本地断开
```

### 判定逻辑（反汇编 `libbluetooth_jni.so` 得到）

```c
// 0x62eb38 起
w20 = getCotaRegionCustBooleanFeature("persist.vendor.bluetooth.mipp.supported", /*default*/...);
__system_property_get("ro.product.device", dev);                    // "yupei"
__system_property_get("persist.vendor.bluetooth.mipp.supported", m); // "yupei"

w8 = w20 | (strcmp(dev, m) == 0);
if (w8) goto support_mipp;                       // ← 行号 924，日志就出自这里

// 否则继续比对机型代号列表
if (dev in {yudi, sheng, uke, muyu, dizi, ruan, flute, organ}) goto support_mipp;
goto not_support;
```

### 关键坑：`getCotaRegionCustBooleanFeature` 不读 property 的值

它把入参当作**特性名**，去查小米的区域定制配置 XML：

```
/system/lib64/libskuparser_cpp.so
    getCotaRegionCustBooleanFeature(name, default)
        -> GetProperty("ro.miui.region")            // CN
        -> GetProperty("persist.sys.cota.carrier")  // 空
        -> 查 /mi_ext/product/etc/cust_features/*.xml   （/mi_ext/product -> /product）
```

配置加载顺序（`libskuparser_ffi.so` 内的路径表）：

```
/mi_ext/product/etc/cust_features/cust_sim_features.xml
/mi_ext/product/etc/cust_features/device_features.xml      ← mipp 在这里，值为 true
/mi_ext/product/etc/cust_features/cust_features.xml
/mi_ext/product/etc/cust_features/cn/cust_features.xml     ← 只有 2 项，不含 mipp
/mi_ext/product/etc/cust_features/<region>/cust_features.xml
/mi_ext/product/opcust/<carrier>/cust_features.xml
```

因为 `cn/cust_features.xml` 里没有覆盖 mipp，最终生效的就是
`device_features.xml` 里的 `true`。

**所以 `setprop persist.vendor.bluetooth.mipp.supported false` 完全无效** ——
代码根本不看这个 property 的值。

## 修复

改一个布尔值：

```xml
<!-- /product/etc/cust_features/device_features.xml -->
- <bool name="persist.vendor.bluetooth.mipp.supported">true</bool>
+ <bool name="persist.vendor.bluetooth.mipp.supported">false</bool>
```

`support_mipp` 变 false 后，蓝牙栈跳过 MIPP 分支，走标准 `/dev/uhid`，
内核创建 `/dev/input/eventX`，外设即正常工作。

### 验证（修复后）

```
/proc/bus/input/devices:
  N: Name="M585/M590 Keyboard"
  N: Name="M585/M590 Mouse"

dumpsys bluetooth_manager:
  XX:XX:XX:XX:95:31 : Selected transport=2 HID connection state=0 HOGP connection state=2
                                                                  ^^^^^^^^^^^^^^^^^^^^ 已连接
```

## 使用

```bash
# 应用修复（改完需重启才生效）
python3 scripts/fix_ble_hid_mipp.py --serial gaokun3 --adb ./platform-tools/adb.exe

# 改完直接重启
python3 scripts/fix_ble_hid_mipp.py --serial gaokun3 --adb ./platform-tools/adb.exe --reboot

# 只检查不改
python3 scripts/fix_ble_hid_mipp.py --serial gaokun3 --adb ./platform-tools/adb.exe --dry-run

# 还原成原始配置（true）
python3 scripts/fix_ble_hid_mipp.py --serial gaokun3 --adb ./platform-tools/adb.exe --revert
```

脚本首次运行会把原始文件备份到 `/data/local/tmp/custbackup/device_features.xml.orig`
（原始 md5 `4b3cb8055955d5b06ec905a792690102`）。备份一旦存在不会被覆盖，
以免用改过的文件覆盖真·原始备份。

## 持久性

改动写在 **super 分区的 `product_a` 逻辑分区**里（`/dev/block/dm-2` ← `nvme0n1p11`），
是真实磁盘存储：

- ✅ **重启不丢失**
- ⚠️ **重新刷机 / OTA 覆盖 product 分区后会丢失**，届时重跑脚本即可

## 走过的弯路（记录，避免重复）

| 尝试 | 为什么不行 |
|---|---|
| `setprop persist.vendor.bluetooth.mipp.supported false` | 代码读的是 XML，不是 property 的值 |
| `ksud sepolicy patch` 放行 bluetooth 读 `vendor_default_prop` | 规则生效了（`Access denied` 消失），但代码仍不读 property |
| 改 `n83/p81c/mipp.pen.supported` | 这三个 key 该函数根本不用 |
| overlayfs / bind mount 替换 `libbluetooth_jni.so` | 蓝牙进程在独立 mount namespace，且 APEX linker namespace 拒绝 `dlopen`，报 `library not found` |
| 替换 `/system/apex/com.android.bt.apex` 里的 SO | **APEX 有小米私钥签名**。运行时只重启蓝牙进程能"骗过"校验，但**整机重启时 apexd 强制校验失败 → 卡开机动画** |
| 重新编译 APEX | 需要小米私钥签名，不可能拿到 |

## 附：相关现象（同为移植缺陷）

排查过程中发现同一类问题：

- **WiFi 扫不到某些热点**：荣耀 Magic6 热点 BSSID 是随机 MAC（本地管理地址，
  如 `b6:2a:fd:bd:db:d3`），`libwifi-hal` / 扫描结果解析层把这类 BSSID 丢弃。
  `iw dev wlan0 scan` 能看到，`cmd wifi list-scan-results` 看不到。
- **NTFS 中文文件名乱码**：`ntfs3` 默认 `iocharset=iso8859-1`，需显式加 `iocharset=utf8`。
