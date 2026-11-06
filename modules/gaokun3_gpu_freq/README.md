# KernelSU 模块：gaokun3 HyperOS GPU 频率调度

GPU devfreq `min_freq` 调度模块，从 `gaokun3_audio_fix` 拆分而来。

## 解决什么问题

GPU（Adreno，`/sys/class/devfreq/3d00000.gpu`）只有 `simple_ondemand` 一个
governor（`performance`/`userspace` 编成 `=m` 但设备上没有 `.ko`）。在
1600×2560@120Hz 的 UI 滑动负载下，simple_ondemand 的 50ms 轮询升频不够积极，
GPU 只在 270/547 MHz 间跳，导致掉帧。实测（Settings 列表滚动）：

| min_freq | gfxinfo 90th | missed vsync |
|---:|---:|---:|
| 270 MHz（默认） | 13 ms | 3 |
| 547 MHz | 15 ms | 1 |
| 690 MHz | 5–6 ms | 0 |

本模块通过设置 `min_freq` 来保底 GPU 不会降到某个频率以下。

## 两种模式

### `fixed`（默认）—— 固定锁频

把 GPU `min_freq` 钉在一个固定值。8 档可选：

| 频率 | 适用场景 |
|---|---|
| 270 MHz | 最省电，适合不需要流畅 UI 的场景 |
| 410 / 500 / 547 MHz | 折中 |
| 606 / 640 / 655 MHz | 偏性能 |
| **690 MHz**（默认） | 最高档，最流畅，但 GPU 永不降频 |

### `dynamic` —— 息屏降频 / 亮屏高频

守护进程每 2 秒轮询背光亮度（`/sys/class/backlight/ae96000.dsi.0/brightness`）：
- 亮屏（brightness > 0）→ `min_freq = SCREEN_ON_FREQ`（默认 690 MHz）
- 息屏（brightness = 0）→ `min_freq = SCREEN_OFF_FREQ`（默认 270 MHz）

兼顾滑动流畅和待机功耗。

## 配置（两种方式）

### 方式一：WebUI 图形界面（推荐）

在 KernelSU / ReSukiSU 管理器 App 里找到本模块，点击模块条目上的 **WebUI / 网页设置** 图标，
打开图形配置页面：

- **模式切换**：固定锁频 / 动态切换
- **8 档频率选择**（固定模式）：270 / 410 / 500 / 547 / 606 / 640 / 655 / 690 MHz
- **动态模式参数**：亮屏频率、息屏频率、轮询间隔
- **实时状态**：当前 min_freq / cur_freq / 屏幕状态 / 守护进程
- 点"应用并保存"立即生效，无需重启

> WebUI 通过 KernelSU 的 `kernelsu` JS API 以 root 执行 shell 命令，
> 配置写入 `/data/adb/gaokun3_gpu_freq.conf`（持久，模块更新不丢失）。

### 方式二：命令行

编辑 `config.conf`（模块目录下），改完执行 `apply.sh` 立即生效：

```bash
# 编辑配置
adb shell su -c 'vi /data/adb/modules/gaokun3_gpu_freq/config.conf'

# 立即生效
adb shell su -c 'sh /data/adb/modules/gaokun3_gpu_freq/apply.sh'
```

### 切换到动态模式示例

```bash
adb shell su -c 'sed -i "s/^MODE=fixed/MODE=dynamic/" /data/adb/modules/gaokun3_gpu_freq/config.conf'
adb shell su -c 'sh /data/adb/modules/gaokun3_gpu_freq/apply.sh'
```

### 持久化配置（模块更新不丢失）

模块目录下的 `config.conf` 在模块更新时会被覆盖。如需保留自定义配置：

```bash
# 把当前 config.conf 复制到持久位置
adb shell su -c 'sh /data/adb/modules/gaokun3_gpu_freq/apply.sh save'

# 之后修改 /data/adb/gaokun3_gpu_freq.conf 即可，脚本优先读它

# 回退到模块默认值
adb shell su -c 'sh /data/adb/modules/gaokun3_gpu_freq/apply.sh reset'
```

## 文件说明

| 文件 | 作用 | 执行时机 |
|---|---|---|
| `module.prop` | 模块元信息 | — |
| `config.conf` | 默认配置（8 档频率 + 模式开关） | 被脚本读取 |
| `post-fs-data.sh` | 早期应用 min_freq（SF 启动前） | post-fs-data |
| `service.sh` | fixed 模式写入 / dynamic 模式起守护进程 | boot_completed |
| `apply.sh` | 运行时重新读取配置并生效 | 手动执行 |
| `uninstall.sh` | 卸载时恢复 min_freq 到 270 MHz 并杀守护进程 | 模块卸载 |
| `webroot/index.html` | WebUI 图形配置页面（在管理器里打开） | 用户打开 |

## 打包

⚠️ **`module.prop` 必须是 zip 里的第一个条目**（ksud 按顺序解压）。

```bash
cd modules/gaokun3_gpu_freq
zip -X ../../gaokun3_gpu_freq.zip module.prop
zip -X -g ../../gaokun3_gpu_freq.zip config.conf \
    post-fs-data.sh service.sh apply.sh uninstall.sh \
    webroot/index.html
```

## 安装

```bash
adb push gaokun3_gpu_freq.zip /data/local/tmp/
adb shell su -c 'ksud module install /data/local/tmp/gaokun3_gpu_freq.zip'
adb reboot
```

## 更新（覆盖安装不可靠，先删再装）

```bash
adb shell su -c 'rm -rf /data/adb/modules/gaokun3_gpu_freq /data/adb/modules_update/gaokun3_gpu_freq'
adb shell su -c 'ksud module install /data/local/tmp/gaokun3_gpu_freq.zip'
adb reboot
```

## 验证

```bash
# 当前 min_freq
adb shell su -c 'cat /sys/class/devfreq/3d00000.gpu/min_freq'

# 当前实际频率
adb shell su -c 'cat /sys/class/devfreq/3d00000.gpu/cur_freq'

# 守护进程状态（dynamic 模式）
adb shell su -c 'cat /data/adb/gaokun3_gpu_freq.pid 2>/dev/null && ps -A | grep -f /data/adb/gaokun3_gpu_freq.pid'

# 查看配置
adb shell su -c 'sh /data/adb/modules/gaokun3_gpu_freq/apply.sh'

# 日志
adb shell su -c 'logcat -d -s gpu_freq'
```

## 卸载

```bash
adb shell su -c 'ksud module uninstall gaokun3_gpu_freq'
adb reboot
# 或手动：
adb shell su -c 'rm -rf /data/adb/modules/gaokun3_gpu_freq'
adb reboot
```
