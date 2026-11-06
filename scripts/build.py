#!/usr/bin/env python3
# Run in the ARM64 privileged container, /work = this tutorial's build directory.
import os, sys, re, shutil, struct, hashlib, subprocess, zipfile, urllib.request
from pathlib import Path
from patch_xiaomi_va_os4 import patch
R=Path('/work'); A=R/'assets'; I=R/'input'; O=R/'out'; W=R/'work'
C=Path('/mnt/candidate'); T=Path('/mnt/stock'); B=Path('/mnt/crdroid')
S=C/'system/system'; P=C/'product'; E=C/'system_ext'; V=C/'vendor'

def run(*args, **kw):
    return subprocess.run(list(map(str,args)),check=True,**kw)
def label(p,typ='system_file'):
    os.setxattr(p,'security.selinux',f'u:object_r:{typ}:s0\0'.encode(),follow_symlinks=False)
def write(p,text,mode=0o644,typ='system_file'):
    if not p.parent.exists():
        write_dir(p.parent,typ)
    p.write_text(text); p.chmod(mode); os.chown(p,0,0); label(p,typ)
def write_dir(p,typ='system_file'):
    if not p.parent.exists():write_dir(p.parent,typ)
    p.mkdir(exist_ok=True); p.chmod(0o755); os.chown(p,0,0); label(p,typ)
def mount(img,dest,ro=False):
    dest.mkdir(parents=True,exist_ok=True)
    run('mount','-o','loop,ro' if ro else 'loop',img,dest)
def props(p,vals):
    lines=[x for x in p.read_text().splitlines()
           if x.partition('=')[0].rstrip('?') not in vals
           and not re.match(r'^log\.tag\.[^=]+=S$',x)]
    p.write_text('\n'.join(lines)+'\n'+''.join(f'{k}={v}\n' for k,v in vals.items()))
def native(p):
    data=p.read_bytes();new,sites=patch(data)
    if sites:
        with p.open('r+b') as f:f.write(new)
        print('VA guard:',p,len(sites),flush=True)
    return data,new,sites

def probe_labels():
    img=W/'selinux-probe.img';dest=Path('/mnt/label-probe')
    with img.open('wb') as f:f.truncate(16*1024**2)
    run('mkfs.ext4','-q','-F',img)
    mount(img,dest)
    try:
        p=dest/'probe';p.write_text('probe');label(p)
    except OSError as error:
        raise RuntimeError('Host rejected Android SELinux xattrs; use a Linux VM with SELinux disabled (e.g. Ubuntu).') from error
    finally:
        run('umount',dest);img.unlink()

def stage():
    O.mkdir(exist_ok=True); W.mkdir(exist_ok=True); (R/'reports').mkdir(exist_ok=True)
    assert not (O/'system.img').exists(),'Use an empty output directory.'
    probe_labels()
    # WSL2 只给 8 个 loop 设备且 docker 自占 2 个，输入镜像按需分批挂、用完即卸；
    # 输出镜像除 system_ext 外保持挂载留给 adapt 使用。
    needs={'system':('system','mi_ext','mi_product'),
           'system_ext':('system_ext','mi_ext'),
           'product':('product','mi_ext','mi_product')}
    mount(I/'crdroid-system.img',B,True)
    for name,size in [('system',1800),('system_ext',1500),('product',8200),('vendor',384)]:
        img=O/f'{name}.img'
        if name=='vendor':
            assert (I/'crdroid-vendor.img').stat().st_size<=size*1024**2, 'Vendor image exceeds allocated partition.'
            shutil.copyfile(I/'crdroid-vendor.img',img)
            with img.open('r+b') as f:f.truncate(size*1024**2)
            run('resize2fs',img)
            mount(img,C/name)
            continue
        for n in needs[name]:
            mount(I/'pad9'/f'{n}.img',T/n,True)
        with img.open('wb') as f:f.truncate(size*1024**2)
        run('mkfs.ext4','-q','-F','-b','4096','-I','256','-N','12000','-m','0',
            '-O','^metadata_csum_seed,^orphan_file','-L',name,img)
        mount(img,C/name)
        run('cp','-a',str(T/name)+'/.',str(C/name)+'/')
        if name=='system':
            for n in ('system_ext','product','vendor'):
                d=C/'system'/n
                if d.is_symlink():d.unlink()
                d.mkdir(exist_ok=True)
            d=C/'system/mi_ext'
            if d.is_symlink():d.unlink()
            write_dir(d)
            for child in (T/'mi_ext').iterdir():
                if child.name in ('system','system_ext','product'):
                    alias=d/child.name;alias.symlink_to('/'+child.name);label(alias)
                else:run('cp','-a',child,d)
        src=T/'mi_ext'/name
        if src.is_dir():run('cp','-a',str(src)+'/.',str(S if name=='system' else C/name)+'/')
        if name=='product' and (T/'mi_product/product').is_dir():
            run('cp','-a',str(T/'mi_product/product')+'/.',str(P)+'/')
        for n in needs[name]:
            run('umount',T/n)
        if name=='system_ext':
            run('umount',C/name)
    shutil.copyfile(S/'framework/framework-res.apk',W/'framework-res.apk')
    (W/'overlays').mkdir(exist_ok=True)
    # Export only APKs that OverlayConfig actually scans.
    for n,f in enumerate(sorted((P/'overlay').rglob('*.apk'))):
        shutil.copyfile(f,W/'overlays'/f'{n:03d}.apk')
    mount(O/'system_ext.img',C/'system_ext')   # 卸过又挂回，留给 adapt 用
    print('Stage complete; now build the RRO and config.xml on the host.')

def usb():
    deps={
      'baksmali':'org/smali/baksmali/2.5.2/baksmali-2.5.2.jar',
      'smali':'org/smali/smali/2.5.2/smali-2.5.2.jar',
      'dexlib2':'org/smali/dexlib2/2.5.2/dexlib2-2.5.2.jar',
      'util':'org/smali/util/2.5.2/util-2.5.2.jar',
      'jcommander':'com/beust/jcommander/1.64/jcommander-1.64.jar',
      'guava':'com/google/guava/guava/27.1-android/guava-27.1-android.jar',
      'antlr-runtime':'org/antlr/antlr-runtime/3.5.2/antlr-runtime-3.5.2.jar'}
    d=W/'smali';d.mkdir(exist_ok=True)
    for name,path in deps.items():
        target=d/f'{name}.jar'
        if not target.is_file():
            for attempt in range(5):
                try:
                    urllib.request.urlretrieve('https://repo.maven.apache.org/maven2/'+path,target)
                    if target.stat().st_size>1000:break
                except Exception as error:
                    print('retry',name,error,flush=True)
            else:raise RuntimeError(f'Cannot download {name}.jar')
    jar=S/'framework/services.jar'
    with zipfile.ZipFile(jar) as z:
        print('services.jar sha256:',hashlib.sha256(jar.read_bytes()).hexdigest(),flush=True)
        (W/'classes3.dex').write_bytes(z.read('classes3.dex'))
    cp=str(d/'*');sm=W/'usb-smali'
    run('java','-cp',cp,'org.jf.baksmali.Main','d',W/'classes3.dex','-o',sm)
    f=sm/'com/android/server/usb/UsbService.smali';text=f.read_text()
    assert text.count('"/sys/class/android_usb"')==1
    f.write_text(text.replace('"/sys/class/android_usb"','"/sys/class/udc"'))
    run('java','-cp',cp,'org.jf.smali.Main','a',sm,'-o',W/'usb.dex')
    tmp=W/'services-new.jar'
    with zipfile.ZipFile(jar) as src,zipfile.ZipFile(tmp,'w') as dst:
        for info in src.infolist():
            dst.writestr(info,(W/'usb.dex').read_bytes() if info.filename=='classes3.dex' else src.read(info.filename))
    with jar.open('wb') as f:f.write(tmp.read_bytes())
    for base in [S/'framework',S/'framework/arm64',S/'framework/oat/arm64']:
        for name in ['services.odex','services.vdex','services.art','services.jar.fsv_meta']:
            (base/name).unlink(missing_ok=True)

def apex():
    out=S/'etc/gaokun-apex';write_dir(out);mnt=Path('/mnt/apex-scan');records=[]
    runtime=None
    for f in sorted((S/'apex').iterdir()):
        if f.suffix not in ('.apex','.capex'):continue
        with zipfile.ZipFile(f) as z:
            if 'original_apex' in z.namelist():
                a=W/'original.apex';a.write_bytes(z.read('original_apex'))
            else:a=f
        img=W/'apex-payload.img'
        with zipfile.ZipFile(a) as z:img.write_bytes(z.read('apex_payload.img'))
        mount(img,mnt,True)
        try:
            if f.stem=='com.android.runtime':
                runtime=W/'runtime.img';shutil.copyfile(img,runtime)
            src=mnt/'lib64/libutils.so'
            if not src.exists():continue
            data=src.read_bytes();new,sites=patch(data)
            if not sites:continue
            dst=out/f'{f.stem}-libutils.so';dst.write_bytes(new);dst.chmod(0o644);label(dst,'system_lib_file')
            records.append((f.stem,hashlib.sha256(data).hexdigest(),dst.name))
        finally:run('umount',mnt)
    text='#!/system/bin/sh\n'
    for module,sha,name in records:
        text+=f'''for target in /apex/{module}*/lib64/libutils.so; do
 [ -f "$target" ] || continue
 sum=$(sha256sum "$target") || exit 1
 [ "${{sum%% *}}" != "{sha}" ] || mount -o bind /system/etc/gaokun-apex/{name} "$target" || exit 1
done
'''
    write(out/'adapt.sh',text)
    assert runtime is not None
    return runtime

def policy(runtime):
    cil=S/'etc/selinux/plat_sepolicy.cil';text=cil.read_text()
    text+='''
(type gaokun_bootdiag)
(typeattributeset domain (gaokun_bootdiag))
(roletype r gaokun_bootdiag)
(typepermissive gaokun_bootdiag)
(allow init gaokun_bootdiag (process (transition)))
(allow system_server ashmem_libcutils_device (chr_file (open)))
(allow hal_audio_default ashmem_libcutils_device (chr_file (open)))
; ── untrusted_app 基础域的 ashmem / prop 权限 ────────────────────────────────
; 症状：Edge 155（com.microsoft.emmx）点图标闪一下立刻回桌面。没有崩溃弹窗、
; 没有 ANR、crash buffer 和 tombstone 都是空的，进程是"干净退出"的：
;   E ashmem  : Unable to open ashmem device: Permission denied
;   E chromium: [ERROR:.../history_service.cc:2019]
;               HistoryService::Init() failed by way of VisitDelegate::Init failing
;   I Zygote  : Process 17592 exited cleanly (0)
;
; 根因是 SELinux 拒绝：
;   avc: denied { open } for path="/dev/ashmem<uuid>"
;     scontext=u:r:untrusted_app:s0:c40,c257,c512,c768
;     tcontext=u:object_r:ashmem_libcutils_device:s0 tclass=chr_file permissive=0
;
; 本机 plat_sepolicy.cil 里 ashmem 的 open 是按 targetSdk 拆域授予的，最高只到
; untrusted_app_34：
;   (allow untrusted_app_34 ashmem_libcutils_device (chr_file (open)))
;   ..._32 / _30 / _29 / _27 / _25
; 而 plat_seapp_contexts 有一条：
;   user=_app minTargetSdkVersion=37 domain=untrusted_app type=app_data_file levelFrom=all
; Edge 155 的 targetSdk=37，匹配不到任何 untrusted_app_3x 版本域，落到【基础域
; untrusted_app】—— 这个域在整份策略里一条 ashmem 规则都没有。
;
; 授给基础域而不是逐个补版本域：以后 targetSdk 38/39/40 的应用只要
; seapp_contexts 没有对应版本域，就都落这里，不会再复现同一个坑。
;
; 后两条是 Chromium 启动时的探测，非致命，只为消除日志噪音：
;   qemu_hw_prop —— Chromium 探测自己是否跑在模拟器里（ro.kernel.qemu）
;   proc_version —— SentryDeviceInf 线程读 /proc/version
; ⚠️ 只授 ashmem_libcutils_device，不授 ashmem_device：最小权限。
; 日志里被拒的路径 /dev/ashmem<uuid> 标签就是 ashmem_libcutils_device
; （见 plat_file_contexts:59），Chromium/Edge 只用这个节点，不需要 /dev/ashmem。
; 顺带说明：本机 cil 里那条 (neverallow base_typeattr_490 ashmem_device
; (chr_file (open))) 实际拦不住东西 —— neverallow 出现在 base_typeattr_490
; 定义之前，编译时该属性还没有类型绑定。实测 (allow domain ashmem_device
; (chr_file (open))) 都能通过 secilc -N。所以不授 ashmem_device 是权限最小化
; 的主动选择，不是因为编译会报错。
(allow untrusted_app ashmem_libcutils_device (chr_file (open read write getattr map ioctl)))
(allow untrusted_app qemu_hw_prop (file (read getattr open map)))
(allow untrusted_app proc_version (file (read getattr open map)))
; audioserver 在 AOSP 里通过 libcutils 的 ashmem_create_region() 拿 AudioTrack
; 的控制块。本机 plat_sepolicy.cil 只给了 appdomain execute，audioserver 域
; 一条 ashmem 规则都没有，于是 createTrack_l() 在 initCheck 处返回 -12
; （"no control block?"），任何走 AudioTrack 的应用都建不出音轨。
; 后果最明显的是字节系播放器（红果短剧 libttmplayer）：它是音视频同步架构，
; 音轨建不出来就直接不开始解码 —— 表现为界面正常、视频区纯黑。
; 另外 audioserver 还要读这两个属性来初始化输出设备。
(allow audioserver ashmem_libcutils_device (chr_file (open read write getattr map ioctl)))
(allow audioserver ashmem_device (chr_file (open read write getattr map ioctl)))
(allow audioserver bootanim_system_prop (file (read getattr map)))
(allow audioserver vendor_default_prop (file (read getattr map open)))
(allow system_server gaokun_bootdiag (fd (use)))
''';cil.write_text(text)
    classes=dict(re.findall(r'\(class (\S+) \(([^()]*)\)\)',(B/'system/etc/selinux/plat_sepolicy.cil').read_text()))
    for p in [cil,E/'etc/selinux/userdebug_plat_sepolicy.cil']:
        if not p.exists():continue
        def edit(m):
            name,perms=m.groups();extra=sorted(set(classes.get(name,'').split())-set(perms.split()))
            return '(class '+name+' ('+perms+(' '+' '.join(extra) if extra else '')+'))'
        p.write_text(re.sub(r'\(class (\S+) \(([^()]*)\)\)',edit,p.read_text()))
    root=C/'system';rt=Path('/mnt/runtime');mount(runtime,rt,True)
    binds=[(E,root/'system_ext'),(P,root/'product'),(V,root/'vendor'),(rt,root/'apex/com.android.runtime'),(Path('/dev'),root/'dev')]
    for src,dst in binds:
        dst.mkdir(parents=True,exist_ok=True);run('mount','--bind',src,dst)
    paths=['/system/etc/selinux/plat_sepolicy.cil','/system/etc/selinux/mapping/202504.cil',
      '/system_ext/etc/selinux/system_ext_sepolicy.cil','/product/etc/selinux/product_sepolicy.cil',
      '/vendor/etc/selinux/plat_pub_versioned.cil','/vendor/etc/selinux/vendor_sepolicy.cil',
      '/system/etc/selinux/plat_sepolicy_genfs_202504.cil']
    try:
        run('chroot',root,'/apex/com.android.runtime/bin/linker64','/system/bin/secilc',
            '-m','-M','true','-G','-N','-c','33',*paths,'-o','/dev/pad9-policy','-f','/dev/null',
            env=dict(os.environ,LD_LIBRARY_PATH='/system/lib64:/apex/com.android.runtime/lib64/bionic'))
    finally:
        for _,dst in reversed(binds):run('umount',dst)
        run('umount',rt)
    dst=V/'etc/selinux/precompiled_sepolicy';shutil.copyfile('/dev/pad9-policy',dst);label(dst,'vendor_file')
    for base,name in [(S,'plat'),(E,'system_ext'),(P,'product')]:
        d=base/'etc/selinux';fs=[d/f'{name}_sepolicy.cil',d/'mapping/202504.cil']
        sha=hashlib.sha256(b''.join(f.read_bytes() for f in fs if f.exists())).hexdigest()+'\n'
        fn=f'{name}_sepolicy_and_mapping.sha256';write(d/fn,sha)
        write(dst.with_name(dst.name+'.'+fn),sha,typ='vendor_file')

def adapt():
    assert S.is_dir() and (W/'Gaokun3FrameworkOverlay.apk').is_file()
    vals={'ro.sf.lcd_density':'240','persist.miui.density_v2':'240','ro.miui.notch':'0',
      'persist.graphics.egl':'angle','debug.hwui.renderer':'skiagl',
      'debug.renderengine.backend':'skiaglthreaded','ro.build.characteristics':'tablet',
      'persist.sys.usb.config':'adb','persist.adb.tcp.port':'5555',
      'persist.bluetooth.a2dp_offload.disabled':'true','ro.bluetooth.a2dp_offload.supported':'false',
      'persist.vendor.qcom.bluetooth.enable.splita2dp':'false','persist.sys.disable_rescue':'true',
      'persist.debug.wfd.enable':'0','persist.sys.sf.color_saturation':'1.0','persist.sys.gradient_blur_perf':'false',
      'persist.sys.background_blur_supported':'false','ro.surface_flinger.supports_background_blur':'0'}
    for p in [S/'build.prop',E/'etc/build.prop',P/'etc/build.prop']:props(p,vals)
    props(S/'build.prop',{'ro.hardware.gralloc':'minigbm','ro.hardware.vulkan':'freedreno',
      'ro.zygote':'zygote64_32','ro.adb.secure':'0','ro.debuggable':'0','ro.mediaserver.64b.enable':'true',
      'ro.miui.product.home':'com.miui.home','ro.product.device':'yupei','ro.product.name':'yupei',
      'ro.product.model':'Xiaomi Pad 9'})
    ident={}
    # stage 结束时已卸掉全部 /mnt/stock 挂载；这里临时挂回 mi_ext 读小米身份属性
    run('mount','-o','loop,ro',I/'pad9/mi_ext.img',T/'mi_ext')
    for line in (T/'mi_ext/etc/build.prop').read_text().splitlines():
        if '=' not in line or line.startswith('#'):continue
        k,v=line.split('=',1)
        if k.startswith(('ro.mi.','ro.miui.','ro.ai.','ro.com.google.')) or k in [
          'ro.product.mod_device','ro.build.version.incremental','ro.product.build.version.incremental',
          'ro.build.version.smr_baseversion','persist.sys.pre_startup']:ident[k]=v
    run('umount',T/'mi_ext')
    props(P/'etc/build.prop',ident)
    for p in [P/'app/Updater',E/'etc/init/miupdater.rc']:
        if p.is_dir():shutil.rmtree(p)
        else:p.unlink(missing_ok=True)
    p=S/'build.prop';p.write_text('\n'.join(l for l in p.read_text().splitlines() if not l.startswith('media.settings.xml='))+'\n')
    p=S/'etc/init/graphicsengine.rc';p.write_text(p.read_text().replace('    class core animation','    class core animation\n    disabled'))
    for abi in ['lib64','lib']:
        for name in ['libEGL_angle.so','libGLESv1_CM_angle.so','libGLESv2_angle.so']:
            src=B/'system'/abi/name
            if src.exists():run('cp','-a',src,S/abi/name)
    write(E/'etc/init/gaokun-hyperos.rc','''on post-fs-data
    setprop sys.usb.config adb
    setprop service.adb.tcp.port 5555
    setprop persist.debug.wfd.enable 0
    setprop debug.renderengine.backend skiaglthreaded
    setprop persist.sys.background_blur_supported false
    # SurfaceFlinger 空闲降频。默认无触摸时把 renderRate 压到 20 Hz，且恢复慢，
    # 于是滑动全程跑在 20 fps 上。实测 dumpsys gfxinfo framestats：120 帧的
    # FrameInterval 全部是 50.00 ms；dumpsys SurfaceFlinger 连续采样显示
    # renderRate 在 120/20 之间反复横跳。这三个值由 SF 启动时读取，
    # post-fs-data 早于 SF，位置正确。修复后 90th 13ms→6ms、missed vsync 27→0。
    setprop debug.sf.set_idle_timer_ms 1000000
    setprop debug.sf.set_touch_timer_ms 1000000
    setprop debug.sf.enable_frame_rate_override false
    # drm_hwcomposer 每个 validate 周期都重复打
    # "Encountered multiple cursor planes for CRTC 90. Ignoring plane 84"，
    # 实测 74 行/秒（30 秒 2230 行），而 "Failed to create DrmKmsPlan" 计数为 0
    # —— 重复的 cursor plane 只是被跳过，合成完全正常，纯属日志噪音。
    # 抬高该 tag 到 ERROR 后 drmhwc 输出 0 行/10 秒，系统总日志量 -60%。
    setprop log.tag.drmhwc E

on property:sys.boot_completed=1
    setprop sys.usb.config adb
    # 刷新率设置必须走 `settings`（binder 调用）。init 自身域没有写 settings
    # 的权限，所以用项目已有的 typepermissive 域 gaokun_bootdiag 执行。
    # HyperOS 的 MiuiRefreshRatePolicy 读 secure 命名空间的这两个键，并以
    # RenderVote 的形式把上限投给 DisplayModeDirector。只写 system 的
    # peak/min_refresh_rate 不生效（实测：SurfaceFlinger 仍停在 60 Hz 的
    # display mode hwcId=3，120 Hz 模式 hwcId=2 永不被选中）。
    exec - root root -- /system/bin/sh /system/etc/gaokun-refresh.sh
    # GPU 最低频率锁在最高档 690 MHz。
    # mainline msm 的 GPU devfreq 只有 simple_ondemand（内核里
    # CONFIG_DEVFREQ_GOV_PERFORMANCE/USERSPACE 编成 =m，但设备上没有对应
    # .ko，所以 available_governors 只剩 simple_ondemand），实测：
    #   1600x2560@120Hz 桌面连续滑动，min_freq=270（默认）
    #     → GPU 只在 270/547 MHz 之间跳，从不升到 606 以上；
    #       gfxinfo 90th 13ms、95th 18ms、missed vsync 3
    #   min_freq=547 → 90th 15ms、95th 18ms、missed vsync 1
    #   min_freq=690 → 90th 5ms、95th 5-6ms、missed vsync 0、GPU 50th 1ms
    # 只有满频才把 120 Hz 下 8.33 ms 的预算用满，547 档不够。代价是功耗，
    # 但 GPU 空闲时本来就在最低档，这里的差别只在有负载时体现。
    write /sys/class/devfreq/3d00000.gpu/min_freq 690000000
''')
    write(S/'etc/gaokun-refresh.sh','''#!/system/bin/sh
# 开机把刷新率钉到 120 Hz。settings 是 binder 调用，必须从非 init 域跑；
# 本文件由 gaokun-hyperos.rc 里的 exec 拉起（见那里关于 gaokun_bootdiag 的说明）。
settings put secure miui_refresh_rate 120
settings put secure user_refresh_rate 120
settings --user 0 put system is_smart_fps 0
settings --user 0 put system min_refresh_rate 120.0
settings --user 0 put system peak_refresh_rate 120.0

# 显示大小 320 / 字号 1.25。刷 super 会格式化 userdata，SettingsProvider 里的
# display_density_forced 和 font_scale 跟着被清空，所以每次开机重放一遍。
#
# 密度必须走 `wm` 而不是 `settings put secure display_density_forced`：实测后者
# 只改设置项、不改变生效值（dumpsys window 的 mForcedDensity 和 dumpsys display
# 的 logical density 都停在旧值），只有 `wm density` 会同时写设置并让
# WindowManager 重新应用。
#
# 240 是系统 / MIUI 的共同基准（build.prop 的 ro.sf.lcd_density /
# persist.miui.density_v2 保持 240 不动），320 仅是用户显示大小覆盖。
# 桌面（Flutter）用自己的逻辑宽度排布，图标尺寸不受密度影响，这一项只放大
# 设置等系统 UI。
wm density 320
settings --user 0 put system font_scale 1.25
''',mode=0o755)
    for dest,src in [(P/'overlay/Gaokun3FrameworkOverlay.apk',W/'Gaokun3FrameworkOverlay.apk'),(P/'overlay/config/config.xml',W/'overlay-config.xml')]:
        write_dir(dest.parent);shutil.copyfile(src,dest);dest.chmod(0o644);label(dest)
    xml=(A/'display.xml').read_text()
    d=P/'etc/displayconfig';write_dir(d)
    for p in set(d.glob('display_id_*.xml'))|{d/'default.xml',d/'display_id_0.xml'}:write(p,xml)
    for name,pkg,cls in [('gaokun-components','com.xiaomi.finddevice','com.xiaomi.finddevice.v2.FindDeviceStatusManagerProvider'),
      ('gaokun-powerkeeper','com.miui.powerkeeper','com.miui.powerkeeper.thermal.ThermalService')]:
        write(S/f'etc/sysconfig/{name}.xml',f'<permissions><component-override package="{pkg}"><component class="{cls}" enabled="false" /></component-override></permissions>\n')
    unavailable=['sensor.light','sensor.compass','location.gps','telephony','telephony.gsm','telephony.cdma','nfc']
    write(V/'etc/permissions/gaokun3-unavailable-features.xml','<permissions>'+''.join(
      f'<unavailable-feature name="android.hardware.{x}" />' for x in unavailable)+'</permissions>\n',typ='vendor_configs_file')
    write(V/'etc/permissions/android.hardware.usb.host.xml','<permissions><feature name="android.hardware.usb.host" /></permissions>\n',typ='vendor_configs_file')
    for src,dst in [('bootlog.sh','etc/gaokun-bootlog.sh'),('bootlog.rc','etc/init/init.gaokun-bootlog.rc')]:write(S/dst,(A/src).read_text())
    for p in [S/'lib64/libutils.so',P/'lib64/libutils.so',S/'bin/gsid']:
        assert native(p)[2],f'No known pointer guard: {p}'
    usb();runtime=apex()
    p=S/'etc/init/netbpfload.rc';text=p.read_text();assert text.count('    exec_start bpfloader\n')==1
    p.write_text(text.replace('    exec_start bpfloader\n',
      '    exec u:r:gaokun_bootdiag:s0 root root -- /system/bin/sh /system/etc/gaokun-apex/adapt.sh\n    exec_start bpfloader\n'))
    # lights HAL: 把 BACKLIGHT 亮度算法从 RGB Rec.601 加权改成 state.color 低字节。
    # 修复 HyperOS 8 位灰度值下拖动亮度滑块时骤黑。
    # 本补丁针对 crDroid rc.1/rc.2 的 lights 二进制（sha e607397f…，与 rc.1 设备实测一致）。
    # 4 字节指令修改 0x53087d08 -> 0x39400048 (ldrb w8,[x2])，偏移 0x37094。
    # 老版 crDroid 基线 (20261003184648) 的 lights sha 是 d549cd52…、偏移 0x370a0，已不再用。
    # 版本再变则按 device/huawei/gaokun3/lights/Lights.cpp 源码修改并重新构建，不套用本偏移。
    f=V/'bin/hw/android.hardware.light-service.gaokun3';data=f.read_bytes()
    assert hashlib.sha256(data).hexdigest()=='e607397fcc384a330d47ff939577e37a0594a2c92e7c217d3a24d487e453ca5c', 'Rebuild lights from source for this vendor version.'
    assert struct.unpack_from('<I',data,0x37094)[0]==0x53087d08
    data=bytearray(data);struct.pack_into('<I',data,0x37094,0x39400048)
    with f.open('r+b') as h:h.write(data)
    policy(runtime)
    run('sync')
    for name in ['vendor','product','system_ext','system']:run('umount',C/name)
    for name in ['system','system_ext','product','vendor']:
        result=subprocess.run(['e2fsck','-fy',str(O/f'{name}.img')])
        assert result.returncode in (0,1,2),f'ext4 error: {name}'
    print('Adapt complete; pack the four images into super.')

if __name__=='__main__':
    {'stage':stage,'adapt':adapt}[sys.argv[1]]()
