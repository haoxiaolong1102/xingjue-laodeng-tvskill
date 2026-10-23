# 已验证固件与广告路径

## 适用范围与可复核产物

案例验证日期：2026-10-21 至 2026-10-23。Redmi A50 2025，实际 model `MiTV-ASTP0`，product `mulan`，HyperOS `OS2.0.19.0.PSTAATV`，Android 9／API 28，`armeabi-v7a`。
这里只发布脱敏发现，不附用户设备日志、原机 APK 或截图。下面的哈希用于核对相同产物；其他产物需要重新检查。

| 原机产物 | SHA-256 |
| --- | --- |
| MiTVSettings3 APK | `2e559b6e25c529fbc1992e214b7b0a6d632d8338158906d47d44e7b2c51aa214` |
| 原厂 TVHome APK | `f0a5b149db71ba5660a69bccdd89859668fee13f3a03065ded64fb8d3af04986` |
| Hyper screensaver APK | `80ddababff71633fcccc3f234c7ad94e1fdc3de4c9aa2c9be5f56996c93ce16a` |

读取路径示例：`adb -s "$TV_SERIAL" shell pm path com.xiaomi.mitv.settings`。先确认包名；保留 split 清单，不把一个 base.apk 当作完整应用。逆向只围绕当前问题取证。

## 静置后的相册广告

该固件的链路：

1. 最后一次用户输入后约 480 秒，PowerManagerService 发 `com.duokan.intent.action.show.screensaver`。
2. `com.xiaomi.tv.gallery/.services.ScreenSaverReceiver` 启动 `.view.ScreenSaverActivity`。
3. 同窗口出现 `AD-PLUGIN-MiAdClient`、`onAdLoaded`、`requestStreamAd`。这些证明广告请求；可见视频由用户反馈确认。
4. `com.xiaomi.mitv.hyper.screensaver` 的 MainReceiver 也收到广播，但相册主题分支直接返回。单看名字会找错目标。

原机 MiTVSettings3 的 `DeviceNameSetting.setScreenSaverTimer(int)` 将官方“关闭”映射为 `system screen_saver_timeout=-1`；原值 `480000`。这才是本案例修改这个键的依据。

使用设置 helper 保存原值后改为 -1。退出正在运行的相框并回 Home，避免旧定时任务／已打开的屏保继续显示。相册、相框应用与手动入口保留，**自动定时相框也随这个计时关闭**。

不改 `screen_off_timeout`、`sleep_timeout` 来保持假唤醒。Android `secure screensaver_enabled=0` 本身不能证明拦住 OEM 广播路径。

案例修改后连续静置约 611 秒：16 次前台采样均为 Tigris，用户活动时间不变，连续日志没有上述广播、相册启动或广告请求。本次未重启；两天后读回仍为 -1。不能把这次观察写成所有固件永久保证。

## 开机与官方系统广告开关

| 标识 | 此固件上的含义／处理 |
| --- | --- |
| `system boot_ad` | 运行时播放状态，**不作为总开关修改** |
| `system boot_ad_switch` | 冷启动广告门，缺省按 1；案例改为 0 |
| `system boot_ad_sound_enable` | 开机广告声音，案例 1 → 0 |
| `system boot_ad_switch_show` | 官方广告开关入口可见性；临时 0 → 1，完成后恢复 0 |
| `persist.sys.adswitch` | 官方 UI 关闭系统广告后读回 0；不凭猜测直接 setprop |
| `global individual_privacy_enabled` | 条款接受状态，**不是个性化广告开关** |
| `global mitv.settings.advertise.state` | 旧版七天关闭逻辑，不作为永久方案 |

流程：保存原值 → 临时显示入口 → 打开官方账号／授权管理 UI → 读取当前屏幕和确认文案 → 关闭广告 → 读回结果 → 检查／重新设开机门 → 恢复入口可见性。

此固件可进入：

```sh
adb -s "$TV_SERIAL" shell am start -a mitv.intent.action.ACCOUNT_AUTH_MANAGER \
  -n com.mitv.tvhome/com.mitv.tvhome.business.account.AuthManageActivity
```

用设置 helper 分别记录临时入口和开机门的修改；临时入口结束就 restore，保留最终开机门记录。UI 路径每一步取新状态，不照搬“向下六次”等坐标／次数。

官方 UI 出现“已关闭系统广告”，同时通知广告 SDK 更新内部状态。它可能把 `boot_ad_switch` 写回 1，所以 UI 操作后重新读取，再生成最终 gate=0 计划，不能用 UI 之前的过期计划。`persist.sys.adswitch` 本身不在 helper allowlist 内，恢复通过同一官方 UI。

案例经用户单独允许重启一次，用户确认无开机广告、自动进入大时钟桌面；property=0 仍保持。普通设置修改不隐含重启授权，也不能推断视频应用内部广告被移除。

## 不具备因果证据的部分

TVManager 自动清理紧邻相册启动，但日志仅证明另一路 `startapps_completed_boost` → `OPERATION_REQUEST_BOOST_SILENCE` → `ShortcutBoostService`；不能声称相册导致清理。它的独立“内存自动清理”开关已关闭。详见 [性能参考](performance.md)，保留共享组件。
