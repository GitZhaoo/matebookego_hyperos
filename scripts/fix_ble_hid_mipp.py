#!/usr/bin/env python3
"""修复荣耀/小米等 BLE HID 外设（鼠标、键盘）配对后无响应的问题。

背景
----
移植版 HyperOS 把机型伪装成 yupei（小米 Pad 9），于是小米的蓝牙栈
（packages/modules/MiuiBluetooth）在 `bta_hh_co_open` 里判定"本机支持妙享笔
（MIPP）"，所有 HOGP(BLE) HID 设备都会被强制走 MIPP 私有路径：

    bta_hh_co_open()
      -> check_mipp_device() == true
      -> open("/dev/mipp_pen0")            # 华为等非小米硬件上不存在
      -> getTouchFeature()                 # vendor.xiaomi.hw.touchfeature 服务不存在
      -> 整体失败，返回 0
      -> btif_hh: "Failed to open uhid driver"
      -> HidHostService: HID connection state 0 -> GATT_Disconnect -> ACL 断开
      -> 外设"已配对"但完全无响应

判定来源不是 property 的值，而是小米的区域定制配置 XML：

    /product/etc/cust_features/device_features.xml
        <bool name="persist.vendor.bluetooth.mipp.supported">true</bool>

蓝牙栈调用 `android::getCotaRegionCustBooleanFeature("persist.vendor.bluetooth.mipp.supported", ...)`，
该函数把入参当作"特性名"去查 XML（而不是读同名 property），所以改
`setprop persist.vendor.bluetooth.mipp.supported false` 完全没有效果。

修复
----
把 device_features.xml 里这一项改成 false。`support_mipp` 变为 false 后蓝牙栈
跳过 MIPP 分支，走标准 `/dev/uhid` 路径，内核正常创建 /dev/input/eventX，
外设即可工作。已在该机上验证：`M585/M590 Mouse` 输入节点出现、HOGP state=2。

持久性
------
改动写在 super 分区的 product_a 逻辑分区里，**重启不会丢失**。只有重新刷机
（或 OTA 覆盖 product 分区）才会被还原，届时重跑本脚本即可。
"""
import argparse, re, shlex, subprocess

FEATURE = 'persist.vendor.bluetooth.mipp.supported'
TARGET = '/product/etc/cust_features/device_features.xml'
BACKUP = '/data/local/tmp/custbackup/device_features.xml.orig'


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--serial', required=True)
    p.add_argument('--adb', default='adb')
    p.add_argument('--reboot', action='store_true',
                   help='修改后立即重启（否则需手动重启才生效）')
    p.add_argument('--revert', action='store_true',
                   help='从备份还原到原始配置（原始值 true）')
    p.add_argument('--dry-run', action='store_true', help='只检查，不修改')
    a = p.parse_args()

    adb = [a.adb, '-s', a.serial]

    def shell(s):
        return subprocess.check_output(adb + ['shell', 'su -c ' + shlex.quote(s)],
                                       text=True).strip()

    if shell('id -u') != '0':
        p.error('su is not root')

    if a.revert:
        if not a.dry_run:
            shell(f'mount -o rw,remount /product')
            shell(f'cp {BACKUP} {TARGET}')
            shell('sync')
        print('reverted:', shell(f'grep -E "name=.{FEATURE}" {TARGET} || true'))
        if a.reboot and not a.dry_run:
            shell('sync; setprop sys.powerctl reboot')
        return

    # 先看原始状态：确认文件存在、没有明显异常
    if not shell(f'test -f {TARGET} && echo yes || echo no') == 'yes':
        p.error(f'{TARGET} not found')
    before = shell(f'grep -oE "<bool name=.{FEATURE}.>[a-z]+" {TARGET} || echo MISSING')
    print('before:', before)

    # 备份必须放在 /data（持久），这样刷机以外的情况下都能还原；
    # 首次运行才写备份，避免用已经改过的文件覆盖真·原始备份。
    if shell(f'test -f {BACKUP} && echo yes || echo no') != 'yes':
        shell(f'mkdir -p /data/local/tmp/custbackup')
        shell(f'cp {TARGET} {BACKUP}')
        print('backup created:', BACKUP)
        print('backup md5:', shell(f'md5sum {BACKUP}').split()[0])
    else:
        print('backup already exists, keep it:', BACKUP)

    if a.dry_run:
        print('dry-run: no change')
        return

    # 只改这一项，其余 49 行保持原样
    shell(f'mount -o rw,remount /product')
    cmd = (f"sed -i 's|<bool name=\"{FEATURE}\">true</bool>|"
           f"<bool name=\"{FEATURE}\">false</bool>|' {TARGET}")
    shell(cmd)
    shell('sync')

    after = shell(f'grep -oE "<bool name=.{FEATURE}.>[a-z]+" {TARGET} || echo MISSING')
    print('after :', after)
    if 'false' not in after:
        p.error('patch did not apply; check the file manually')

    # XML 结构完整性：行数应保持不变
    print('lines :', shell(f'wc -l < {TARGET}').strip())
    print('md5   :', shell(f'md5sum {TARGET}').split()[0])

    if a.reboot:
        print('rebooting...')
        shell('sync; setprop sys.powerctl reboot')
    else:
        print('done. reboot required for the change to take effect.')


if __name__ == '__main__':
    main()
