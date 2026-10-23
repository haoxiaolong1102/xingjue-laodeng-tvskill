# 应用安装、LibreTV 与新鲜 UI

## 来源和兼容性

仅使用用户指定或项目官方公布的发布源，下载前核对当次 release、资产名称、版本、minSdk、ABI、包名、签名及调试状态。计算 SHA-256 留本地；没有官方 digest 时，自己计算的 hash 只能标识文件，不能独自证明真实性。安装新包与更新旧包分开判断。

```sh
adb -s "$TV_SERIAL" install -r <verified-release.apk>
```

不因更新失败自动 uninstall，避免丢配置。不要把第三方 APK 重新托管成 skill 的附件。

## LibreTV／DpadTV

- [LibreSpark/LibreTV](https://github.com/LibreSpark/LibreTV) 是 Web／服务端项目。在案例日期 2026-10-23 未提供官方 Android TV APK；每次重新检查现状，不把第三方客户端称为官方。
- [AresCNZJ/DpadTV](https://github.com/AresCNZJ/DpadTV) 是第三方遥控器客户端。只有用户选择此方案后才安装；也可根据用户已有 LibreTV URL 采用合适入口。官方项目和客户端版本需要互相兼容。
- 案例 DpadTV 1.2.0，minSdk 23、包名 `com.dpadtv.client`，在 API 28 可安装；APK SHA-256 `8259fc8a1f1c7e9d7ed1efa16c3671b76af9ce7682c4ebe8cfb98227dae9f5b0`。这是历史验证信息，不固定 future latest。源码参考 commit `4dd04cc4e394c808980aeebb2495a5af8d134e74`。

首选用户自己的后端。用户选公开演示站时，从当前上游 README 确认地址、可用性和认证，不把某天的 URL／密码／cookie／第三方采集源写进 skill。示例数据源格式见 [LibreTV Data Sources](https://libretv.is-an.org/wiki/Data-Sources.html)；按用户选择配置有权访问的内容，不承诺演示站长期服务。

通过客户端设置输入 URL／认证信息，先获取状态、再认证、再看推荐／搜索／详情／播放。后端成功不等于电视播放成功。

## 只有已证明 debuggable 时的有限配置手段

案例 release 实际带 `DEBUGGABLE` 标记，`run-as com.dpadtv.client` 可访问**新安装客户端自身**的 SharedPreferences。在 UI 输入故障后，停止该客户端、备份其 `dpadtv_native.xml`，合并修改必要字段、保留其余值，再启动验证。配置应通过 stdin／本地私有文件传入，避免密码出现在命令日志或截图。

这是个别产物的能力，不是通用安装前提；非 debuggable 版本就走 UI。不要尝试 root 或用这个方法访问其他应用的私有数据。正在播放时不擅自 force-stop；配置记录和凭据不公开。恢复用该客户端的原偏好备份或 UI；settings helper 不覆盖 app 私有配置。

## UI 与播放判断

`tv_ui_capture.py` 每次新建输出目录，使用 UUID 远端 XML 并清理自己的临时文件。命令 exit 0、但 stderr 出现 `ERROR: could not get idle state`，应视为 **没有新 XML**。动画或图标编辑模式尤其容易触发；转截图，必要时让用户用遥控器完成。

不要沿用旧 XML 的 focused=true、坐标和节点。DpadTV EditText 的 Down 可能移动光标，并不切换字段；先选择准确控件，输入后核对字段再提交，避免把密码写进 URL。

先完成安装与可用性验证。置顶图标只是可选项：若长按语义／焦点不可靠，有限尝试后用用户遥控器处理，并准确说明目前入口位置。ADB `--longpress CENTER` 不能保证等同实体长按；不要为图标排位反复进入动画编辑导致误移动相邻应用。

播放验证顺序：片源可访问 → 媒体进度持续增长 → 真实视频解码器与音轨 → 用户确认画面／声音。电视硬件视频层可能在 screenshot 里呈黑色，即使真实屏幕播放正常。
本案例用户确认画面声音正常，不能因此推断所有片源或其他后端可用。
