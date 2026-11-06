#!/usr/bin/env python3
# Run on the host with Android SDK build-tools 36.0.0 and JDK on PATH.
import os,re,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
sdk=Path(os.environ['ANDROID_HOME'])/'build-tools/36.0.0';aapt=sdk/'aapt2';w=Path('work')
def run(*a):return subprocess.run(list(map(str,a)),check=True)
run(aapt,'compile','--dir','assets/overlay/res','-o',w/'overlay.zip')
run(aapt,'link','-o',w/'overlay-unsigned.apk','--manifest','assets/overlay/AndroidManifest.xml',
    '-I',w/'framework-res.apk','--auto-add-overlay',w/'overlay.zip')
if not Path('overlay.keystore').exists():
    run('keytool','-genkeypair','-keystore','overlay.keystore','-storepass','android',
        '-keypass','android','-alias','gaokun','-keyalg','RSA','-keysize','2048',
        '-validity','10000','-dname','CN=gaokun3')
run(sdk/'apksigner','sign','--ks','overlay.keystore','--ks-key-alias','gaokun',
    '--ks-pass','pass:android','--key-pass','pass:android','--out',w/'Gaokun3FrameworkOverlay.apk',w/'overlay-unsigned.apk')
props=dict(re.findall(r"^\[(.*?)\]: \[(.*?)\]$",Path("input/crdroid-getprop.txt").read_text(),re.M))
props.update({"ro.product.brand":"Xiaomi","ro.miui.product.home":"com.miui.home"})
rows=[]
for f in sorted((w/'overlays').glob('*.apk')):
    t=subprocess.check_output([str(aapt),'dump','xmltree',str(f),'--file','AndroidManifest.xml'],text=True)
    if 'E: overlay ' not in t:continue
    name=re.search(r':requiredSystemPropertyName\([^)]*\)="([^"]+)"',t)
    value=re.search(r':requiredSystemPropertyValue\([^)]*\)="([^"]+)"',t)
    if name and value and props.get(name[1],"")!=value[1]:continue
    pkg=re.search(r'A: package="([^"]+)"',t)[1]
    static=bool(re.search(r':isStatic\([^)]*\)=true',t))
    priority=re.search(r':priority\([^)]*\)=(\d+)',t)
    rows.append((static,int(priority[1]) if priority else 0,pkg))
# Static overlays must precede all mutable overlays. Among static overlays,
# keep manifest priority order and place our hardware settings last.
root=ET.Element('config')
for static,_,pkg in sorted(rows,key=lambda r:(not r[0],r[1],r[2])):
    if not static:continue
    ET.SubElement(root,'overlay',package=pkg,enabled='true',mutable='false')
ET.SubElement(root,'overlay',package='org.gaokun3.hyperos.framework.overlay',enabled='true',mutable='false')
for static,_,pkg in sorted(rows,key=lambda r:r[2]):
    if static:continue
    ET.SubElement(root,'overlay',package=pkg,enabled='true' if pkg=='com.android.systemui.gesture.line.overlay' else 'false',mutable='true')
assert len({r[2] for r in rows})==len(rows),'Duplicate overlay packages'
(w/'overlay-config.xml').write_text(ET.tostring(root,encoding='unicode')+'\n')
print('RRO signed; overlay configuration generated from original APK manifests.')
