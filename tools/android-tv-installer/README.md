# 星爵老灯tvskill 安卓电视安装助手 1.1.0

安装助手适用 Android 9 或以上。内置 Tigris 1.8 和基于 Marco Movie TV 0.5.23 的「Marco 开放片单」，播放器支持 32 位或 64 位 ARM。两款应用分别经过系统确认安装。播放随包影片无需输入片源或配网。

「桌面与广告设置」打开系统默认主页、Tigris 设置或电视厂商开放的广告设置。设置后用遥控器主页键验证。需要更高权限的固件，使用机型教程中的授权流程。广告按钮本身不修改系统开关。

## 构建

使用 Python 3.11+、JDK 17+、Android API 28 和 SDK build-tools 35.0.0。在本目录运行 `python3 build.py --help`。`upstream-lock.json` 记录各输入的文件名和 SHA-256，构建时会下载其中带 `url` 的上游文件。

从已发布的 [v1.1.0 安装包](https://github.com/haoxiaolong1102/xingjue-laodeng-tvskill/releases/download/v1.1.0/Xingjue-TVSkill-Setup-1.1.0.apk) 提取 `assets/packages/marco-tv.apk`，以 `Marco-Open-Films-TVSkill-1.1.0.apk` 存到 `--vendor` 目录。把发布页的 `Marco-Open-Films-TVSkill-1.1.0-source.zip` 和 `OPEN-FILMS-LICENSES.txt` 放进同一个目录。源码包里的 `TVSKILL.md` 和 `scripts/build_tvskill.py` 记录播放器端的构建步骤。[v1.1.0 发布页](https://github.com/haoxiaolong1102/xingjue-laodeng-tvskill/releases/tag/v1.1.0)

本版 `versionCode` 为 2。用 `--signing-dir` 指定私有目录。本地生成的签名密钥适用于自行安装的版本，覆盖升级须使用现有版本的同一签名。
