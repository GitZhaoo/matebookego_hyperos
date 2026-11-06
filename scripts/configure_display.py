#!/usr/bin/env python3
"""Apply the verified display defaults through rooted ADB; no reboot."""
import argparse,re,shlex,subprocess

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--serial',required=True)
    p.add_argument('--adb',default='adb');p.add_argument('--density',type=int,default=320)
    p.add_argument('--font-scale',type=float,default=1.25);a=p.parse_args()
    adb=[a.adb,'-s',a.serial]
    def shell(s):return subprocess.check_output(adb+['shell','su -c '+shlex.quote(s)],text=True).strip()
    if shell('id -u')!='0':p.error('su is not root')
    size=re.search(r'Physical size:\s*(\d+)x(\d+)',shell('wm size'))
    if not size:p.error('Cannot read physical display resolution')
    for key,value in [('screen_brightness_mode','0'),('display_color_mode','0'),('is_smart_fps','0'),
      ('user_refresh_rate','120'),('min_refresh_rate','120.0'),('peak_refresh_rate','120.0'),('font_scale',str(a.font_scale))]:
        shell(f'settings --user 0 put system {key} {value}')
    # HyperOS 的 MiuiRefreshRatePolicy 读 secure 命名空间的这两个键，并以 RenderVote
    # 的形式把上限投给 DisplayModeDirector。只写 system 的 peak/min_refresh_rate 不会
    # 生效：SurfaceFlinger 会一直停在 60 Hz 那个 display mode（hwcId=3），120 Hz 模式
    # （hwcId=2）永远不会被选中，于是 HWC 只能合成 1 个 plane，其余层全部回退到 GPU
    # client 合成，表现为 UI 卡顿 / 视频像 PPT。两个键必须同时写。
    for key,value in [('miui_refresh_rate','120'),('user_refresh_rate','120')]:
        shell(f'settings put secure {key} {value}')
    # 关闭小米的背景模糊与动态岛模糊：它们各占一个全屏层，8-plane 的 DPU 吃不消。
    for ns,key,value in [('secure','disable_window_blurs','1'),('global','disable_window_blurs','1'),
      ('global','support_dynamic_island_blur','0'),('secure','miui_home_recents_blur_mode','0')]:
        shell(f'settings put {ns} {key} {value}')
    shell('cmd display set-brightness 0.5')
    shell(f'cmd display set-user-preferred-display-mode {size[1]} {size[2]} 120 0')
    # 让 SurfaceFlinger 重新读一遍 display mode，否则当前 session 仍留在 60 Hz 模式。
    shell('setprop ctl.restart surfaceflinger')
    shell(f'wm density {a.density}')
    print(shell('wm density'));print('font_scale:',shell('settings --user 0 get system font_scale'))
    print('secure.miui_refresh_rate:',shell('settings get secure miui_refresh_rate'))
if __name__=='__main__':main()
