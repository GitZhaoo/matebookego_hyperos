#!/usr/bin/env python3
"""Read crDroid block images using binary streams (also safe in PowerShell)."""
import argparse, json, shlex, subprocess
from pathlib import Path

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--serial',required=True)
    p.add_argument('--adb',default='adb')
    p.add_argument('--output',type=Path,default=Path('input'))
    for name in ('system','vendor','super'):p.add_argument(f'--{name}-block')
    a=p.parse_args();adb=[a.adb,'-s',a.serial]
    def shell(cmd):
        return subprocess.check_output(adb+['shell','su -c '+shlex.quote(cmd)],text=True).strip()
    assert shell('id -u')=='0','su is not root'
    slot=shell('getprop ro.boot.slot_suffix')
    if not slot:
        value=shell('getprop ro.boot.slot')
        slot='_'+value if value else ''
    if slot!='_a':raise SystemExit('This build supports Android A only; detected slot '+repr(slot))
    props=subprocess.check_output(adb+['shell','getprop'],text=True)
    if '[ro.build.version.sdk]: [36]' not in props or '[ro.product.vendor.device]: [gaokun3]' not in props:
        raise SystemExit('Expected original gaokun3 Android 16 crDroid. Do not capture the donor/ported system.')
    a.output.mkdir(parents=True,exist_ok=True);records={}
    for role in ('system','vendor','super'):
        custom=getattr(a,role+'_block')
        if custom:
            paths=[shell('readlink -f '+shlex.quote(custom))]
        else:
            name=role+slot if role!='super' else 'super'
            logical=f'/dev/block/mapper/{name}'
            command=f'''for p in {logical} /dev/block/by-name/{name} /dev/block/bootdevice/by-name/{name} /dev/block/platform/*/by-name/{name}; do
 [ -b "$p" ] && readlink -f "$p"
done
true'''
            paths=sorted(set(shell(command).splitlines()))
            # Logical partitions prefer the active device-mapper node.
            if role!='super' and shell(f'if [ -b {logical} ]; then echo yes; fi')=='yes':
                paths=[shell('readlink -f '+logical)]
        if len(paths)!=1 or not paths[0].startswith('/dev/block/'):
            raise SystemExit(f'Ambiguous/missing {role}: {paths}; use --{role}-block /dev/block/...')
        block=paths[0]
        if shell('if [ -b '+shlex.quote(block)+' ]; then echo yes; fi')!='yes':raise SystemExit('Not a block device: '+block)
        size=int(shell('blockdev --getsize64 '+shlex.quote(block)))
        expected=1048576 if role=='super' else size
        if role=='super' and size!=12884901888:raise SystemExit('Unsupported super size: '+str(size))
        dest=a.output/('super-metadata.bin' if role=='super' else f'crdroid-{role}.img')
        if dest.exists():raise SystemExit('Already exists: '+str(dest))
        temp=dest.with_suffix(dest.suffix+'.partial')
        command=('dd if='+shlex.quote(block)+' bs=1048576 count=1 2>/dev/null') if role=='super' else 'cat '+shlex.quote(block)
        print(f'{role}: {block} -> {dest} ({expected} bytes)',flush=True)
        with temp.open('wb') as out:subprocess.run(adb+['exec-out','su -c '+shlex.quote(command)],stdout=out,check=True)
        if temp.stat().st_size!=expected:raise SystemExit('Incomplete read: '+str(temp))
        temp.rename(dest);records[role]={'block':block,'size':size}
    (a.output/'crdroid-getprop.txt').write_text(props,encoding='utf-8')
    (a.output/'source-device.json').write_text(json.dumps({'serial':a.serial,'slot':slot,'partitions':records},indent=2)+'\n')

if __name__=='__main__':main()
