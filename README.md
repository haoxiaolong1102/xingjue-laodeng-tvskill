# 星爵老灯tvskill

> 欢迎使用星爵老灯tvskill！这是“星爵老灯讲AI”的第一个公开 Skill。如果使用中有不合适的地方，欢迎到抖音关注“星爵老灯讲AI”，留言反馈、点个赞。谢谢大家的支持！

让开机后的大屏更清爽，让遥控器用起来更顺手。

**星爵老灯tvskill** 把一台红米电视的实际改造经验，整理成可复用的 Codex Skill：用 **Tigris** 打造大时钟主页和个性背景，结合 **LibreTV 与 DpadTV** 配置观影入口，再通过 ADB 排查广告触发与后台负担。先看设备和证据，再做能恢复的修改。

## Tigris + LibreTV，各司其职

- **Tigris 管主页**：大时钟、应用入口、自定义背景和 Home 守护，打开电视就看到喜欢的桌面。
- **LibreTV 管观影服务**：连接用户选择的 LibreTV 后端；需要遥控器操作时，可搭配第三方电视客户端 DpadTV。LibreTV 本身是 Web／服务端项目，DpadTV 不是它的官方 APK。
- **这个 Skill 把流程串起来**：识别型号、核对兼容性、排查开机与静置广告、优化后台、安装配置，再检查真实画面和声音，留下原值与恢复记录。

Tigris、LibreTV 和 DpadTV 是各自独立的开源项目，本 Skill 整理它们在电视改造中的使用方法。适配以实际型号与固件证据为准。

## 包含什么

- **广告排查**：区别开机广告、OEM 相册屏保、应用内部广告，沿原机 APK 与日志找触发点。
- **Tigris 桌面**：Home 守护、开机进入桌面、16:9 个性背景与时钟留白。
- **后台优化**：优先保留语音、投屏、HDMI、遥控器与播放功能，按场景检查内存、CPU 和进程重启。
- **电视应用**：以 LibreTV／第三方 DpadTV 客户端为案例，检查来源与兼容性并验证真实播放。
- **连接故障修复**：区分演示站 502、接口不兼容和媒体失效；可使用原创电视本机连接服务，检查重启自动恢复，保留原片源与观看记录。
- **恢复与验证**：设备绑定的设置计划、原值记录、冲突检查、新鲜 UI 截图、真实静置观察。

## 安装和使用

需要支持 skills 的 Codex 环境、Python **3.10+**、[Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools) 中的 `adb`、Git，以及同网且由你授权调试的 Android 电视。

```sh
TV_SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/xingjue-laodeng-tvskill"
git clone https://github.com/haoxiaolong1102/xingjue-laodeng-tvskill.git "$TV_SKILL_DIR" &&
  python3 "$TV_SKILL_DIR/scripts/welcome.py"
```

按以上命令安装成功后，终端会显示欢迎语；开始电视改造任务时，Skill 也会在会话开头欢迎一次，然后继续处理你的请求。

在能发现该 skill 的会话里直接说：

> 使用 $xingjue-laodeng-tvskill，检查我的红米电视静置后跳视频的问题，保留语音、投屏、HDMI 和全部应用功能，先诊断再做可恢复的优化。

或要求定制主页、安装用户选定客户端；无需每次做全套。
已经安装过时，在该目录检查自己的改动后 `git pull --ff-only`，不要强制覆盖本地文件。

旧版 `xiaomi-tv-skill` 用户更新时，先保留本地 `state/` 和自己的改动，将技能目录改名为 `xingjue-laodeng-tvskill`，把 origin 更新到本页新仓库地址，再拉取更新；避免同时保留两份技能。旧仓库链接会跳转到新地址。

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
| `tv_dpad_config.py backup/set-server/restore-server` | 对已证明 debuggable 的 DpadTV 私密备份，仅改／恢复服务器地址；回退保留最新观看记录 |

各脚本支持 `--help`、`--adb`。详细执行和恢复步骤见 [SKILL.md](SKILL.md)；未知固件不能直接照抄示例设置。

## 演示站失效时

“请求失败”需要先查服务、客户端接口和媒体地址。本次实测遇到原演示站 HTTP 502；修复后仍使用原 DpadTV，把连接服务放在电视本机运行，电脑不必一直开着。

仓库提供原创 [本机连接服务源码](tools/libretv-bridge/) 和 [诊断、构建、自动恢复与回退流程](references/libretv-repair.md)。它仅监听电视本机地址，公开构建不内置片源、密码或演示站，继续使用用户已有的片源。新装客户端需要按用户选择配置内容源；它实现的是 DpadTV 1.2.0 接口子集，其他版本需核对。

该服务是可选修复方案，构建需 JDK 17、Android API 28 和 SDK build-tools。普通开机广播受固件限制时，可在说明并取得通知访问权限授权后启用生命周期恢复；代码不读取或保存通知内容。自启动必须在手动打开应用前通过实际重启验证。

## 实测范围

| 项目 | 已验证 |
| --- | --- |
| 设备／固件 | Redmi A50 2025，MiTV-ASTP0，Android 9／API 28，HyperOS OS2.0.19.0.PSTAATV |
| 桌面 | Tigris 标准版 v1.8，实体 Home 立即返回；保留原厂桌面 |
| 开机 | 单次获准重启后，用户确认无广告并进入新桌面 |
| 静置 | 修改已证实的 OEM 计时后约 611 秒，16 次前台采样与连续日志未见原相册广告路径 |
| 播放 | DpadTV 1.2.0，用户确认实际画面和声音正常 |
| 连接修复（2026-10-28） | 原客户端安装包保持不变；本机服务在第二次授权重启后自动恢复，推荐／搜索／详情／续播通过复测，原历史保留 |

其他型号／固件需要重新取证。关闭 OEM 屏保计时也会停掉该计时下的自动相框，手动相框仍保留。没有承诺去除视频应用内广告、永久无广告，或固定释放多少内存；也没有宣称所有附加功能都完成实测。

## 开发与来源

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q scripts tests tools/libretv-bridge/build.py
python3 tools/libretv-bridge/build.py --help
```

测试使用临时目录内的模拟 ADB，不连接电视；GitHub Actions 运行同样的离线测试，并独立构建、核验原创辅助 APK。测试覆盖 UTF-8 配置暂存、传输中断和保留新历史的回退，不能代替真机验证。增加固件配置时提供脱敏型号／版本、原机产物哈希、设置语义和验证范围，不上传原机二进制或私人素材。

感谢 [Tigris](https://github.com/lesnolie/Tigris)、[LibreTV](https://github.com/LibreSpark/LibreTV)、[DpadTV](https://github.com/AresCNZJ/DpadTV)。本仓库的原创指引、脚本与本机连接服务采用 [MIT](LICENSE)；第三方项目保留各自许可证，本仓库不分发其 APK 或源码。
