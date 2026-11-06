#!/usr/bin/env python3
"""Read persistent Android logs from the selected userdata partition in USB Linux."""
import argparse,os,subprocess,sys,tempfile
from pathlib import Path
from flash import disk_tree,select_part,idle

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--disk',required=True)
    p.add_argument('--userdata',help='Partition path or PARTUUID=uuid')
    p.add_argument('--output',type=Path,default=Path('bootlogs.tar.gz'));a=p.parse_args()
    if sys.platform!='linux' or os.geteuid()!=0:p.error('Run with sudo in USB Linux')
    node=select_part(disk_tree(a.disk),'userdata',a.userdata);idle(node)
    if node.get('fstype')!='ext4':p.error('Expected unencrypted ext4 userdata')
    if a.output.exists():p.error('Output already exists')
    a.output=a.output.resolve();a.output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='gaokun-logs-') as d:
        root=Path(d);subprocess.run(['mount','-o','ro,noload',node['path'],d],check=True)
        try:
            names=[x for x in ['gaokun-bootlogs','tombstones','system/dropbox','anr'] if (root/x).exists()]
            if not names:raise SystemExit('No persistent logs found; check the logger and userdata partition')
            subprocess.run(['tar','-czf',str(a.output),'-C',d,*names],check=True)
        finally:subprocess.run(['umount',d],check=True)
    print(a.output)
if __name__=='__main__':main()
