# Tigris 桌面、守护与壁纸

上游：[lesnolie/Tigris](https://github.com/lesnolie/Tigris)，以当次 README、AGENTS.md、release 和已安装 APK 为准。
案例安装标准版 v1.8，包名 `com.leslie.tvhome`，release APK SHA-256 `8b57e3fdc215974ad1a06a8e689fbe91cd6ad66786f179abdd462e784f5e7785`。源码参考 commit `2244988c63d991e010001567491ee96b4de99dca`，不假定该 commit 与所有 release 完全一致。

## 安装前后

下载上游 release，核对 SDK／ABI、包名、版本、签名和 SHA-256，再 `adb -s "$TV_SERIAL" install -r <APK>`。更新现有包先考虑配置和签名兼容；不要为了通过安装而自动卸载旧版。

记录原 HOME、`enabled_accessibility_services`、`enabled_notification_listeners`、screensaver、已有权限和 appops；只增加需要的权限。

标准版在该固件用到：

```sh
adb -s "$TV_SERIAL" shell pm grant com.leslie.tvhome android.permission.WRITE_SECURE_SETTINGS
adb -s "$TV_SERIAL" shell cmd notification allow_listener com.leslie.tvhome/com.leslie.tvhome.RevivalListener
adb -s "$TV_SERIAL" shell appops set com.leslie.tvhome SYSTEM_ALERT_WINDOW allow
adb -s "$TV_SERIAL" shell am broadcast -a com.leslie.tvhome.CONFIG \
  -n com.leslie.tvhome/.ConfigReceiver --ez guard true --ez keep_adb false
```

`keep_adb false` 仅是“不要求持续开放调试”的选择，配置已有桌面时先读现值和用户偏好，不能覆盖已明确要求保持 ADB 的设置。电视唤醒后 ADB 可能关闭，让用户重新打开即可。主机 ADB 授权与 Tigris 本机 self-ADB 授权不同，不为安装桌面顺便开启清理能力。

CONFIG guard 代码会合并自身无障碍服务；核实运行版本后使用。无论通过 UI 还是脚本，不能用只有 Tigris 的字符串覆盖全列表，保留 OEM VoiceAccessibilityService 等原有项。

## HOME 的固件差异

在本案例 Android 9，强制 Tigris 为 Android 默认 HOME 导致约 5 秒切换等待。保留 `com.mitv.tvhome/.MainActivityUserMode` 为默认 HOME，再用 HomeGuardService 拦实体 Home，用户验证立即回大时钟桌面。
`Guard.isDefaultHome=true` 时该版 Home 键拦截器直接返回，所以不能“默认 HOME 已改成功”就结束验证。

保留原厂 `com.mitv.tvhome`。它承载共享语音／播放等服务，禁用它可能导致黑屏或功能损失。其他设备只有在实际验证后才能选类似方案，不自动改默认 HOME。

相框相关 Android 设置可为：
`secure screensaver_components=com.leslie.tvhome/com.leslie.tvhome.PhotoDream`，`screensaver_enabled=1`。使用设置 helper 记录原值；如用户仅要求主页，不必开启自动相框。Tigris 在此版读取 OEM `screen_saver_timeout`，提前 15 秒触发相框；值 -1 会同时取消该自动路径。

## 个性化背景

1. 获取当前主页截图，确定时钟、顶部按钮和底部 dock 占位；按实际显示比例制作静态背景，通常 16:9。时钟侧低对比留白，人物／标题置于用户指定侧，保持电视远距离可读。
2. 用户给人物参考需要重新设计时，使用环境可用的 imagegen skill／工具编辑，保留角色和准确文字；没有工具时可使用用户现有合适文件，不假称已生成。最终仍由电视实屏确认裁切与遮挡。
3. 使用 Tigris 自带壁纸页面／同网手机上传入口，避免额外常驻主机服务。案例标准版 `.WallpaperActivity` 会展示含随机 token 的本地临时 URL（有效约五分钟）。从当前界面取得，不记录成固定链接。
4. 当前源码 PhoneServer 的 `GET api/state` 查询选择，multipart `POST api/upload` 字段 `photo` 上传到应用内部并选 `mine`，`POST api/background` 的 id 选背景。接口和 token 路径随版本变化，先查当次源码／本地页面请求，不猜地址。
5. 单张固定背景选择“我的照片”，检查轮换设置；有多张原照片时先询问选哪张或保存选择，不批量删除。退出壁纸页回 Home，确认无需电脑继续开机也可显示。

不要把用户的人物素材、账号卡片、局域网上传 token、原始截图打包到公开 skill；仅带通用设计步骤。

## 恢复

先 `CONFIG --ez guard false`，只传本次要改的字段；按本地记录恢复原 HOME／screensaver，核对原有无障碍项仍在。新加通知监听可用 `cmd notification disallow_listener` 撤销，新加权限才 revoke，appops 恢复原 mode 而不是一律 deny。恢复背景选择通过 UI 完成。
卸载 Tigris 会删除其私有背景／设置，必须在用户要求卸载且原桌面可正常进入时才执行；设置 helper 不负责桌面卸载或图像备份。
