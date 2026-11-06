# MateBook E Go · HyperOS 4 部署项目

把小米平板 9（Pad9 / `yupei`）的 HyperOS 4 系统移植到华为 MateBook E Go
（`gaokun3` / SC8280XP）的完整、可一键刷写的部署工程。

- **底包**：`yupei-ota_full-OS4.0.5.0.XPZCNXM-user-17.0-4fe489f542.zip`
- **硬件基线**：crDroid Android 16 `20261003184648`、内核 `7.2.0-rc2-gaokun3+`
- **保留**：原 kernel / DTB / ramdisk / EFI / vendor HAL
- **产物**：12 GiB `super.raw.img.zst`（liblp 10.2 / 64 KiB metadata / 3 槽）

> 只替换 Android 的 `super` 分区，不动 ESP、boot 和 Windows。首次刷写会清空
> `userdata` 与 `metadata`，请先备份。

---

## 1. 目录

```text
matebookego_hyperos/
├── artifact/                 # 已构建、可直接刷写的部署产物
│   ├── super.raw.img.zst     #   7.5 GB，SHA-256 4744a33a…
│   ├── SHA256SUMS
│   └── modules/              #   ./deploy.sh modules 生成的运行时模块 zip
├── input/                    # 重建所需的原始镜像（Pad9 / crDroid）
│   ├── pad9/                 #   system / system_ext / product / mi_ext / mi_product
│   ├── crdroid-system.img    #   提供 ANGLE 与策略基线
│   ├── crdroid-vendor.img    #   rc.2 vendor（sha a4c84743…）
│   ├── boot.rc2.img          #   对应内核（sha f60c65d2…）
│   ├── super-metadata.bin    #   实机 liblp 几何
│   └── crdroid-getprop.txt
├── scripts/                  # 构建、刷写、抓取、显示校准
│   ├── build.py              #   stage / adapt 主流程
│   ├── build_path_c_docker.sh#   一键构建（Docker，linux/amd64）
│   ├── overlay.py            #   编译并签名 RRO
│   ├── pack_super.py         #   按实机 liblp 封装 super
│   ├── flash.py              #   USB Linux 刷写 super / 格式化数据分区
│   ├── verify_artifact.py    #   镜像 SHA 与分区布局校验
│   ├── pack_modules.py       #   打包 modules/*.zip
│   ├── capture_base.py       #   从原 crDroid 抓取硬件层
│   ├── configure_display.py  #   刷机后 120 Hz / 密度 / 字号
│   └── collect_logs.py       #   卡开机时离线取日志
├── assets/                   # 显示、启动日志、RRO 资源
├── docs/                     # 音频/性能、Edge ashmem、BLE HID 修复记录
├── modules/                  # KernelSU 运行时模块（可选）
│   ├── gaokun3_audio_fix/    #   SurfaceFlinger / 音频策略
│   ├── gaokun3_gpu_freq/     #   GPU min_freq 调节
│   ├── gaokun3_app_ashmem/   #   untrusted_app ashmem 修复
│   └── fix_screenrecorder_privapp/ # 录屏窗口权限修复
├── recovery/                 # 变砖恢复：ESP / boot_a / metadata + RESTORE.md
├── reports/super-layout.json # 分区偏移与容量
├── tests/
├── tools/                    # payload-dumper-go、Windows adb/fastboot
├── bt36/                     # Android build-tools 36（构建 overlay 用）
├── deploy.sh                 # 一键构建 / 校验 / 打包模块
├── flash.sh                  # 一键刷入（USB Linux）
├── Dockerfile
└── CHANGES.md                # 全部系统改动清单
```

指纹 bring-up 实验、上游 crDroid 克隆等非部署内容已移到同级
`_reference/`，避免和可刷写工程混在一起。

---

## 2. 一键刷入（推荐）

先把整个目录拷到平板的 Fedora / Ubuntu USB 系统（至少保留 `artifact/`、
`scripts/`、`flash.sh`），然后在 USB 系统里执行：

```bash
sudo ./flash.sh --list
```

按 `MODEL / TRAN / SIZE` 找到内置 Android 磁盘（不要选 USB 启动盘），先只看计划：

```bash
sudo ./flash.sh --disk /dev/nvme0n1
```

确认计划中的 `super / userdata / metadata` 三个分区正确，再追加 `--write`：

```bash
sudo ./flash.sh --disk /dev/nvme0n1 --write
```

脚本会：

1. 校验压缩镜像 SHA-256；
2. 只写 `super`（12 GiB，四个 A 分区）；
3. 重新格式化 `userdata` 和 `metadata`；
4. 保留 boot / EFI / Windows，不切换 B 槽。

刷完手动重启，在 UEFI / systemd-boot 菜单里选内置盘的 **Android (HyperOS, slot A)**。

分区名不标准时，用 `PARTUUID=` 或实际路径覆盖：

```bash
sudo ./flash.sh --disk /dev/mmcblk0 \
  --super PARTUUID=实际-super-uuid \
  --userdata PARTUUID=实际-userdata-uuid \
  --metadata PARTUUID=实际-metadata-uuid \
  --write
```

---

## 3. 从源码重建

要求：Docker Desktop（Windows）或 Docker Engine（Linux/macOS），支持
`--privileged` 和 loop mount，工作盘至少 **80 GiB** 可用。

```bash
./deploy.sh build
```

流程：清理 `out/ work/ reports/` → 构建/复用 `pad9-port-tools:amd64` →
`stage` → 编译 RRO → `adapt` → 封装 super → 校验 → 晋升到 `artifact/`。

常用命令：

```bash
./deploy.sh verify     # 校验 artifact 镜像、分区布局、关键输入
./deploy.sh promote    # 手动把 out/ 的结果晋升到 artifact/
./deploy.sh modules    # 生成 artifact/modules/*.zip
```

只校验现有产物：

```bash
python3 scripts/verify_artifact.py --check-inputs
```

构建脚本使用 `bt36/` 里的 x86_64 Android build-tools，因此容器固定
`linux/amd64`；`adapt` 阶段的 `secilc` 在容器内 chroot 到 arm64 Android 根，
依赖 Docker Desktop 的 qemu-aarch64 binfmt（已实测可用）。

> 本仓库只包含源码、脚本和文档。`input/`、`artifact/`、`bt36/`、
> `tools/platform-tools/`、`recovery/*.img` 及签名密钥均已在 `.gitignore`
> 中排除，需要按上文自行准备或从官方 ROM 解包。

如需从官方 ROM 重新解包（当前 `input/pad9/` 已解好，可跳过）：

```bash
tools/payload-dumper-go.exe -p system,system_ext,product,mi_ext,mi_product \
  -o input/pad9 官方ROM.zip
```

---

## 4. 刷机后设置

首次开机后，用有线/无线 ADB 连接：

```bash
adb devices -l
python3 scripts/configure_display.py --serial 实际序列号
```

它会设置手动中间亮度、自然色彩、固定 120 Hz、用户密度 320、字号 125%。
密度和刷新率也已写进系统开机脚本，通常无需重复执行。

### 可选运行时模块

系统镜像已经包含核心修复（音频、120 Hz、Edge ashmem、GPU 频率）。
只有不想重刷 super 时，才用模块补：

```bash
./deploy.sh modules
adb push artifact/modules/gaokun3_audio_fix.zip /data/local/tmp/
adb shell su -c 'ksud module install /data/local/tmp/gaokun3_audio_fix.zip'
adb reboot
```

---

## 5. 恢复

`recovery/RESTORE.md` 记录了变砖恢复步骤，并附带：

| 文件 | 用途 |
|---|---|
| `esp.img` | 恢复 ESP（gk3boot + systemd-boot + 启动项） |
| `boot_a.img` | 恢复 Android A 槽 boot |
| `metadata.img` | 恢复 Android metadata |

只在前述分区路径经 `lsblk` / `sgdisk` 核对后再 `dd`。旧 rc.1 的完整 super
已剔除，避免把失败版本混进部署产物。

---

## 6. 验证范围与已知限制

已在实机验证：桌面、开发者选项、ADB、亮度、触摸、120 Hz 硬件合成、
扬声器/麦克风、Edge 启动、视频播放。

未验证 / 已知问题：

- 相机、长期稳定性、休眠唤醒未做完整回归；
- 指纹未纳入本部署（相关实验代码已移出）；
- 硬件视频编码按设计关闭，`screenrecord` 报 codec 错误属预期；
- HyperOS 的部分小米服务（如跨机型 OTA）已主动移除。

细节与定位过程见：

- [docs/audio-and-performance-fixes.md](docs/audio-and-performance-fixes.md)
- [docs/edge-ashmem-fix.md](docs/edge-ashmem-fix.md)
- [docs/ble-hid-mipp-fix.md](docs/ble-hid-mipp-fix.md)
- [CHANGES.md](CHANGES.md)

---

## 7. 产物指纹

```text
artifact/super.raw.img.zst
  SHA-256 4744a33a658260eadd3b92a15948ba98a09a3a4d4ba71560b6e7b3a15433f2d5
  size    7,497,874,996 bytes

input/crdroid-vendor.img
  SHA-256 a4c84743379ebce2695bd021dbaefde8526b68af418c3506641d6e50c6e11b80

input/boot.rc2.img
  SHA-256 f60c65d2fdd03b601ba1819efebdab165b51bbc630995131f350b35fa873e603
```

---

## 8. 致谢

本项目能够运行，离不开社区此前的 gaokun3 Android 移植工作。特别感谢
**[vahiru/gaokun-android](https://github.com/vahiru/gaokun-android)**：
其内核、DTB、boot 与硬件适配为本次 HyperOS 4 移植提供了关键基础。

同时感谢 crDroid、KernelSU 以及小米 HyperOS 相关开源社区的工作。
