# 恢复指南（ESP / boot / metadata 备份）

本目录保留的是 rc.2 基线（HyperOS super 之外）的启动资产，全部经过设备端与
主机端 SHA-256 校验。旧 rc.1 的完整 super 已从部署工程移除。

## 备份内容

| 文件 | 来源分区 | 大小 | SHA-256 |
|---|---|---|---|
| `boot_a.img` | `/dev/block/nvme0n1p9` | 64 MB | `32b267edb8e15fc7c99e6cc4021592604a4e1394ff33c42d9118f45a8838f334` |
| `metadata.img` | `/dev/block/nvme0n1p8` | 32 MB | `c95d8e65920c2a232b0689c004a413958b9cc0bbbd0573a38aa1b41d45225ca4` |
| `esp.img` | `/dev/block/nvme0n1p1` | 300 MB | `39b77205aa50d87a86009320f13d48ecfbc7cd553642cc87f2e06297aff73439` |
| `getprop.txt` | `getprop` 全量 | — | — |
| `cmdline.txt` | `/proc/cmdline` | — | — |
| `partition_table.txt` | `sgdisk --print` | — | — |
| `esp_loader_config.txt` | ESP loader/entries/gk3boot 配置 | — | — |

`boot_b.img` 与 `boot_a.img` 完全相同，已去重。

## 启动流

UEFI → systemd-boot（`loader.conf` 默认 `*-android-a.conf`）→
`/EFI/gk3boot/0.2.0-e5.g3d0cb032e81a/gk3boot.efi`
（`gk3.hint=a gk3.dispatch=1`）→ 从 ESP 根加载 `/Image` + `/initrd.img` +
`/sc8280xp-huawei-gaokun3.dtb`。

`boot_a/b`（`ANDROID!` 镜像）不被 bootloader 直接使用，只供 Android OTA/hash。
当前槽：A；SELinux enforcing；verity disabled。

## 恢复场景

### 1. 只改了 ESP / boot，系统不启动

```bash
# 先确认分区编号与 partition_table.txt 一致
sudo dd if=esp.img of=/dev/nvme0n1p1 bs=1M conv=fsync
sudo dd if=boot_a.img of=/dev/nvme0n1p9 bs=1M conv=fsync
sync
```

重启后选 **Android (HyperOS, slot A)**。super / userdata 未动。

### 2. super 被写坏

用当前部署产物重刷（会重新格式化 userdata / metadata）：

```bash
cd ..
sudo ./flash.sh --disk /dev/nvme0n1 --write
```

`metadata.img` 只用于「super 与 userdata 都保持原状、仅 metadata 分区损坏」
的极端情况；不要把它与新格式化的 userdata 混用：

```bash
sudo dd if=metadata.img of=/dev/nvme0n1p8 bs=1M conv=fsync
sync
```

### 3. ESP 启动项被破坏，进不了任何系统

`esp.img` 含完整 gk3boot + systemd-boot + 启动项（Android A、Fastboot、Windows）。
dd 回 ESP 后再按场景 1 恢复 boot_a。

## 前置确认

- 任何 `dd` 前用 `lsblk` / `sgdisk --print /dev/nvme0n1` 核对 GPT PARTLABEL：
  `esp / boot_a / boot_b / super / metadata / userdata`。
- 写 ESP 后若 vfat 报脏：`sudo fsck.vfat -a /dev/nvme0n1p1`。
- 操作前先把 recovery 文件复制到 USB 工作副本，不要直接改原文件。
