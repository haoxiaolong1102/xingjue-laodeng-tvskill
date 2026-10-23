# xiaomi-tv-skill

把一台红米电视的实际改造过程，整理成可复用的 Codex skill：定位广告来源，换大时钟主页和背景，优化后台，安装电视应用，并保留恢复方法。

它是一套由 agent 按设备证据执行的流程，附带 ADB 工具；不是点一下就适配所有固件的刷机包。

## 包含什么

- **广告排查**：区别开机广告、OEM 相册屏保、应用内部广告，沿原机 APK 与日志找触发点。
- **Tigris 桌面**：Home 守护、开机进入桌面、16:9 个性背景与时钟留白。
- **后台优化**：优先保留语音、投屏、HDMI、遥控器与播放功能，按场景检查内存、CPU 和进程重启。
- **电视应用**：以 LibreTV／第三方 DpadTV 客户端为案例，检查来源与兼容性并验证真实播放。
- **恢复与验证**：设备绑定的设置计划、原值记录、冲突检查、新鲜 UI 截图、真实静置观察。

## 安装和使用

需要支持 skills 的 Codex 环境、Python **3.10+**、[Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools) 中的 `adb`、Git，以及同网且由你授权调试的 Android 电视。

```sh
git clone https://github.com/haoxiaolong1102/xiaomi-tv-skill.git \
  "${CODEX_HOME:-$HOME/.codex}/skills/xiaomi-tv-skill"
```

在能发现该 skill 的会话里直接说：

> 使用 $xiaomi-tv-skill，检查我的红米电视静置后跳视频的问题，保留语音、投屏、HDMI 和全部应用功能，先诊断再做可恢复的优化。

或要求定制主页、安装用户选定客户端；无需每次做全套。
已经安装过时，在该目录检查自己的改动后 `git pull --ff-only`，不要强制覆盖本地文件。

ADB 连接需电视端打开调试并允许计算机；菜单因固件不同。先 `adb devices -l` 确认设备，网络调试按实际地址连接。不要向公网开放 ADB。

## 脚本手动使用

在仓库根目录执行，先把变量换成 `adb devices -l` 显示的精确目标 serial：

```sh
TV_SERIAL='替换为目标设备serial'
python3 scripts/tv_snapshot.py --serial "$TV_SERIAL" --output state/before.json
```

脚本只处理显式指定的设备，不扫描网络。所有输出保存在本地、默认 mode 0600，`state/` 等目录已忽略。不要提交原始快照／日志／截图；里面可能有设备标识、账号、Wi-Fi 和内容记录。

| 脚本 | 用途 |
| --- | --- |
| `tv_snapshot.py` | 只读设备基线、设置、前台、内存和服务状态 |
| `tv_settings.py plan/apply/restore` | 六个明确键的原值记录、逐项读回与冲突保护；不是万能恢复工具 |
| `tv_idle_verify.py` | 不发按键、不加 wakelock 的连续日志与周期采样；时长／日志／输入不合格即不判通过 |
| `tv_ui_capture.py` | 新建 UUID XML，检查 exit 0 的 idle 错误，另存 PNG；不复用旧 UI |

各脚本支持 `--help`、`--adb`。详细执行和恢复步骤见 [SKILL.md](SKILL.md)；未知固件不能直接照抄示例设置。

## 实测范围

| 项目 | 已验证 |
| --- | --- |
| 设备／固件 | Redmi A50 2025，MiTV-ASTP0，Android 9／API 28，HyperOS OS2.0.19.0.PSTAATV |
| 桌面 | Tigris 标准版 v1.8，实体 Home 立即返回；保留原厂桌面 |
| 开机 | 单次获准重启后，用户确认无广告并进入新桌面 |
| 静置 | 修改已证实的 OEM 计时后约 611 秒，16 次前台采样与连续日志未见原相册广告路径 |
| 播放 | DpadTV 1.2.0，用户确认实际画面和声音正常 |

其他型号／固件需要重新取证。关闭 OEM 屏保计时也会停掉该计时下的自动相框，手动相框仍保留。没有承诺去除视频应用内广告、永久无广告，或固定释放多少内存；也没有宣称所有附加功能都完成实测。

## 开发与来源

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q scripts tests
```

测试使用临时目录内的模拟 ADB，不连接电视；GitHub Actions 运行同样的离线测试。它验证工具边界和恢复逻辑，不能代替真机验证。增加固件配置时提供脱敏型号／版本、原机产物哈希、设置语义和验证范围，不上传原机二进制或私人素材。

感谢 [Tigris](https://github.com/lesnolie/Tigris)、[LibreTV](https://github.com/LibreSpark/LibreTV)、[DpadTV](https://github.com/AresCNZJ/DpadTV)。本仓库的原创指引与脚本采用 [MIT](LICENSE)；第三方项目保留各自许可证，本仓库不分发其 APK 或源码。
