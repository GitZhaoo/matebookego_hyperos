#!/usr/bin/env python3
"""USB Linux only: inspect a disk, then explicitly write super/reset Android data."""
import argparse, hashlib, json, os, stat, subprocess, sys
from pathlib import Path
SUPER_SIZE=12884901888

def run(*args,**kw):return subprocess.run(list(map(str,args)),check=True,**kw)
def disk_tree(disk):
    disk=str(Path(disk).resolve())
    obj=json.loads(subprocess.check_output(['lsblk','--json','--bytes','--paths','--output',
      'PATH,SIZE,TYPE,PARTLABEL,PARTUUID,FSTYPE,MOUNTPOINTS,MAJ:MIN',disk],text=True))['blockdevices']
    if len(obj)!=1 or obj[0]['type']!='disk':raise ValueError('--disk must be a whole physical disk, not a partition')
    return obj[0]
def select_part(tree,role,override=None):
    # Select direct partitions of this disk, never a global by-partlabel symlink.
    parts=[n for n in tree.get('children',[]) if n['type']=='part']
    if override and override.upper().startswith('PARTUUID='):
        matches=[n for n in parts if (n.get('partuuid') or '').lower()==override.split('=',1)[1].lower()]
    elif override:
        resolved=str(Path(override).resolve());matches=[n for n in parts if n['path']==resolved]
    else:
        matches=[n for n in parts if (n.get('partlabel') or '').lower()==role]
    if len(matches)!=1:raise ValueError(f'{role}: {len(matches)} matches on {tree["path"]}; specify --{role} PATH or PARTUUID=uuid')
    return matches[0]
def idle(part):
    def check(node):
        if any(node.get('mountpoints') or []):raise ValueError('Mounted device: '+node['path'])
        for child in node.get('children',[]):check(child)
    check(part)
    holders=Path('/sys/dev/block')/part['maj:min']/'holders'
    if holders.is_dir() and any(holders.iterdir()):raise ValueError('Device has active holders: '+part['path'])
    loops=json.loads(subprocess.check_output(['losetup','--json','--output','NAME,BACK-FILE'],text=True))
    for node in loops.get('loopdevices') or []:
        backing=node.get('back-file')
        if backing and str(Path(backing).resolve())==part['path']:raise ValueError('Loop device uses '+part['path'])
    actual=os.stat(part['path'])
    if not stat.S_ISBLK(actual.st_mode):raise ValueError('Not a block device')
    if f'{os.major(actual.st_rdev)}:{os.minor(actual.st_rdev)}'!=part['maj:min']:raise ValueError('Device identity changed')
    size=int(subprocess.check_output(['blockdev','--getsize64',part['path']],text=True))
    if size!=part['size']:raise ValueError('Device size changed')
def plan(a):
    tree=disk_tree(a.disk);targets={role:select_part(tree,role,getattr(a,role)) for role in ('super','userdata','metadata')}
    if len({x['path'] for x in targets.values()})!=3:raise ValueError('Three distinct partitions are required')
    for node in targets.values():idle(node)
    for role in ('userdata','metadata'):
        if targets[role].get('fstype') not in (None,'ext4'):
            raise ValueError(f'{role}: expected ext4 or an unformatted Android partition; refusing another filesystem')
    if targets['super']['size']!=SUPER_SIZE:raise ValueError('This port requires a 12 GiB super partition')
    if targets['userdata']['size']<4*1024**3:raise ValueError('userdata unexpectedly small')
    if not 16*1024**2<=targets['metadata']['size']<=256*1024**2:raise ValueError('metadata size outside supported range')
    return {'disk':tree['path'],'image':str(a.image.resolve()),'targets':targets,
      'action':'write super; format userdata and metadata; keep boot/EFI; reboot manually'}
def verify(image,checksums):
    hashes=[]
    for line in checksums.read_text().splitlines():
        words=line.split(maxsplit=1)
        if len(words)==2 and Path(words[1].lstrip('*')).name==image.name:hashes.append(words[0])
    if len(hashes)!=1 or len(hashes[0])!=64:raise ValueError('Expected exactly one image checksum in SHA256SUMS')
    with image.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
    if actual.lower()!=hashes[0].lower():raise ValueError('Compressed image checksum mismatch')
    print('Compressed SHA-256 verified.',flush=True)
def write_super(image,node):
    # O_EXCL rejects an already claimed block device. Bound writes to its exact size.
    fd=os.open(node['path'],os.O_WRONLY|os.O_EXCL);proc=None;written=0;next_report=0
    try:
        proc=subprocess.Popen(['zstd','-dc','--',str(image)],stdout=subprocess.PIPE)
        while written<SUPER_SIZE:
            data=proc.stdout.read(min(8*1024**2,SUPER_SIZE-written))
            if not data:raise ValueError(f'Short raw image: {written}/{SUPER_SIZE}')
            view=memoryview(data)
            while view:
                count=os.write(fd,view);view=view[count:]
            written+=len(data)
            if written>=next_report:
                print(f'{written}/{SUPER_SIZE} bytes',flush=True);next_report=written+128*1024**2
        if proc.stdout.read(1):raise ValueError('Raw image exceeds super partition size')
        if proc.wait()!=0:raise ValueError('zstd decompression failed')
        os.fsync(fd)
    finally:
        if proc and proc.poll() is None:proc.kill();proc.wait()
        if proc and proc.stdout:proc.stdout.close()
        os.close(fd)
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--list',action='store_true',help='Read-only disk inventory')
    p.add_argument('--disk',help='Whole target disk, e.g. /dev/nvme0n1 or /dev/mmcblk0')
    for role in ('super','userdata','metadata'):p.add_argument('--'+role,help='Partition path or PARTUUID=uuid; otherwise match GPT PARTLABEL on --disk')
    p.add_argument('--image',type=Path,default=Path('out/super.raw.img.zst'))
    p.add_argument('--checksums',type=Path,help='Defaults to SHA256SUMS beside the image')
    p.add_argument('--write',action='store_true',help='Actually flash and erase Android data; default only shows a plan')
    a=p.parse_args()
    if sys.platform!='linux':p.error('Run this script in USB Fedora/Ubuntu on the tablet')
    if a.list:
        run('lsblk','-o','PATH,SIZE,FSTYPE,LABEL,PARTLABEL,PARTUUID,MODEL,TRAN,MOUNTPOINTS');return
    if not a.disk:p.error('--disk is required')
    if os.geteuid()!=0:p.error('Run with sudo to inspect raw devices')
    if not a.image.is_file():p.error('Image does not exist: '+str(a.image))
    result=plan(a);print(json.dumps(result,indent=2,ensure_ascii=False),flush=True)
    if not a.write:
        print('Plan only. Add --write to flash and erase Android data.');return
    checksums=a.checksums or a.image.parent/'SHA256SUMS';verify(a.image,checksums)
    # Re-check after the checksum pass before any mutation.
    if plan(a)!=result:raise ValueError('Target changed during verification')
    write_super(a.image,result['targets']['super'])
    for role in ('userdata','metadata'):
        idle(result['targets'][role])
        run('mkfs.ext4','-F','-b','4096','-I','256','-m','0','-L',role,
          '-O','^metadata_csum_seed,^orphan_file',result['targets'][role]['path'])
    run('sync');print('Finished. Reboot manually into the existing Android A entry.')

if __name__=='__main__':
    try:main()
    except (ValueError,OSError,subprocess.CalledProcessError) as error:raise SystemExit(str(error))
