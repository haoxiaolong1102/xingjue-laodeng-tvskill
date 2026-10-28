# LibreTV 连接修复与电视本机服务

用于已选用 DpadTV 的连接故障。保持用户的客户端和片源选择；不是要求每次安装都另加服务。

## 先定位故障层

1. 保存只读基线、客户端版本／包名／调试状态、当前地址和原偏好备份。退出正在播放的影片，保护最新续播进度；凭据和观看记录只存本地。
2. 分别检查服务首页、`GET /api/status` 和用户已有片源 API。在电脑和电视均复现相同 502，且片源 API 正常时，可判定本次主要故障在原服务；不是仅凭客户端弹窗下结论。
3. 查当次上游 README／发布说明是否有新地址。替代站必须兼容原客户端的 status、认证、推荐、搜索和详情接口。只有 HTML 200、`/api/status` 为 404 的另一种 TV 服务不能直接替换。
4. 接口可用后还要检查 HLS：主清单、子清单和至少一个实际媒体分片。旧影片的清单或分片 404 属于该媒体地址问题，不等同于整个客户端故障。

有限核实公开替代站，避免无休止搜域名。若没有兼容替代，而用户要求完成修复，可以说明后采用本仓库的独立本机兼容服务；不擅自更换用户片源、创建付费服务或云账号。

## 可选：本机兼容服务

原创源码在 [tools/libretv-bridge](../tools/libretv-bridge/)。它提供 DpadTV 1.2.0 使用的接口子集：状态／本机认证、AppleCMS 搜索与详情、豆瓣推荐、封面、源列表及 M3U 列表。它不是完整 LibreTV 服务端，也不修改原客户端 APK。

- 包名 `com.xingjue.libretvbridge`，入口名“LibreTV 本机连接”，当前源码版本 1.2，最低 API 28。Android 9 真机已验证；其他固件和新客户端需重查后台与接口限制。
- 仅监听电视 `127.0.0.1:17919`，DpadTV 地址为 `http://127.0.0.1:17919`。无需电脑常开或局域网端口；电视仍需联网访问原片源。
- 发布源码不内置片源、密码或演示站。原客户端将用户已有片源随搜索／详情请求提交；新装客户端须按用户选择配置片源。推荐接口不可用且无默认片源时返回空列表，不能冒称已恢复推荐。
- 媒体由原播放器直接播放；服务不代理整段视频，不持有唤醒锁，不做周期轮询。缓存、响应和请求队列有限；搜索最多八个源，每源使用上游返回的一页。不能把接口子集称为全功能 LibreTV。
- 上游请求限公开 HTTP(S)，检查常见私网地址及跳转；不发送客户端密码、cookie 或通知内容。普通启动权限为联网、前台服务和开机广播。

### 构建与安装

需要 JDK 17、Android SDK 的 `platforms;android-28` 和 build-tools（本案例 35.0.0）；从官方 [SDK Manager](https://developer.android.com/tools/sdkmanager) 获取工具，例如 `sdkmanager "platforms;android-28" "build-tools;35.0.0"`。本构建脚本不自动下载、不连接电视。签名和输出放在本地私有状态目录：

```sh
python3 "$TV_SKILL_DIR/tools/libretv-bridge/build.py" \
  --sdk "$ANDROID_SDK_ROOT" --state-dir "$TV_STATE_DIR/bridge-build"
```

SDK 未采用标准目录时，可指定 `--android-jar`、`--build-tools`、`--java-home`。脚本会核验 APK 签名并输出 SHA-256；保留 `bridge-build/signing/` 的密钥和密码，后续更新须使用同一签名。首次生成的密钥只属于该本地安装；不上传签名目录或用户生成的 APK。

检查实际包名、minSdk、版本和当前是否已安装，再用 `adb -s "$TV_SERIAL" install -r <本地构建的APK>`。签名冲突时使用原签名或原安装方式，不以卸载原客户端／辅助服务来绕过错误。

在切换地址前，先打开辅助入口并检查其状态接口。电脑端可临时转发一个空闲端口测试，例如 `adb ... forward tcp:27919 tcp:17919`，检查后立即移除该转发；不要据此声称服务可脱离电脑运行。

优先在 DpadTV 设置页更改地址。仅确认 debuggable、UI 不便操作时使用 helper：

```sh
python3 "$TV_SKILL_DIR/scripts/tv_dpad_config.py" backup --serial "$TV_SERIAL" \
  --output "$TV_STATE_DIR/dpad-backup.json"
# 先正常退出播放器。此命令会停止该客户端，备份并只修改 server_url，不自动重启它。
python3 "$TV_SKILL_DIR/scripts/tv_dpad_config.py" set-server --serial "$TV_SERIAL" \
  --url http://127.0.0.1:17919 --record "$TV_STATE_DIR/dpad-server.json"
adb -s "$TV_SERIAL" shell am start -n com.dpadtv.client/.MainActivity
```

如暂存或读回失败，记录标为 uncertain，先核对同一设备，不继续用初始页面冒称成功。`adb exec-in/exec-out` 的历史尝试曾造成配置不一致，本工具使用 `adb shell -T` 二进制 stdin、无害 UTF-8 标记和原子替换；仍须在重启客户端后实际检查地址、片源和历史。不要把“文件写入成功”当作客户端已采用设置。

## 开机恢复与授权

第一次安装后可手动运行，不把“开机广播已声明”当作自启动成功。小米固件可能在重启时将第三方包标成 `stopped=true`，使普通 `BOOT_COMPLETED` 无法拉起前台服务。

需要自动恢复且确实遇到这个问题时，说明并取得用户对**通知访问权限**的授权。该权限在系统层面能接触通知；本仓库 `RevivalListener` 只实现服务连接／断开回调，用于拉起或重新绑定连接服务，未实现通知内容读取、日志或存储。已有明确授权不重复询问。

保存当前通知监听列表后，使用系统命令只增加本服务，不整表覆盖：

```sh
adb -s "$TV_SERIAL" shell cmd notification allow_listener \
  com.xingjue.libretvbridge/com.xingjue.bridge.RevivalListener
```

核对原有 Tigris 等监听仍存在、辅助监听已绑定、`BridgeService` 为前台服务。仅声明服务或 grant 命令 exit 0 不算完成。

重启会打断画面，需要当前授权覆盖；一次重启验证失败后，不能把该授权当成无限次重启许可。获准后：

1. 记录原 boot ID、辅助 PID、客户端地址和临时调试偏好。若为调试临时调整已验证 Tigris 的 `keep_adb`，保存原值，完成后恢复原值；不要把所有设备默认设为常开 ADB。
2. 重启并仅重连用户指定的设备，等待 `sys.boot_completed=1`。**在手动打开辅助入口或原客户端之前**，检查新 boot ID、辅助 PID、通知监听绑定及前台服务，保存证据。
3. 再检查本机接口。移除电脑测试转发，直接打开原 DpadTV，复测推荐／搜索／详情／播放和续播。手动先拉起辅助应用会掩盖开机恢复失败。
4. 对硬件解码和音轨取证，进度需持续增长；实际画面声音仍由用户确认。只修改生命周期回调且已有当前播放确认时，记录确认对应的版本范围，不伪称用户又确认了一次。
5. 恢复临时调试偏好，确认旧广告／静置设置、无障碍和通知服务保留，留下最终页面与恢复记录。

本案例 Tigris 的开机守护窗口为三分钟。期间 `uiautomator` 连接／断开可能让无障碍守护重新绑定；若看到 `TigrisGuard` 的 `bound after boot` 日志并跳回主页，先结合 uptime、截图和实际前台排查采样干扰。等待该实现的窗口结束再做 XML 检查，不为测试关闭用户的桌面守护；其他版本窗口须查实际实现。

## 回退与交付

回退服务器地址时，helper 将原地址合并到**最新**偏好，保留新增历史和续播。若地址已被用户改为第三个值，它拒绝覆盖：

```sh
python3 "$TV_SKILL_DIR/scripts/tv_dpad_config.py" restore-server --serial "$TV_SERIAL" \
  --record "$TV_STATE_DIR/dpad-server.json"
```

旧地址可能仍故障，恢复地址本身不代表恢复服务。撤销权限时只撤销本次新增的 helper 组件，保留原监听；需要移除新装 helper 时遵循用户授权，不卸载原 DpadTV。保留原始完整备份用于灾难恢复，日常回退不覆盖完整旧 XML。

交付说明原站是否修复、实际采用的服务、是否依赖电脑、用户确认和重启验证范围。一次完整实例不能推断所有固件或所有片源长期可用。

## 脱敏真机验证（2026-10-28）

Redmi A50 2025／MiTV-ASTP0／Android 9／OS2.0.19.0.PSTAATV，原 DpadTV 1.2.0 APK 未修改。原演示站首页和状态接口在电脑与电视均为 502，原片源 API 为 200；没有核实到官方新地址。

本机服务恢复推荐、搜索、详情及媒体播放，用户确认画面声音正常。普通开机广播第一次未恢复，随后获得通知访问及第二次重启授权。第二次重启后，在手动启动任何入口前已确认服务和监听自动恢复；原客户端加载 48 条推荐、测试搜索 6 条结果，续播进度增长约 42.8 秒，硬件解码与音轨正常。此案例有预先选择的源作为默认值；公开构建不包含该配置，空默认源的推荐降级路径另外处理。

核对原有 13 条历史、12 个旧续播位置、片源和凭据字段保留。辅助服务在本次播放时 PSS 采样约 10.6 MiB，仅为该窗口观测；临时 ADB 偏好和电脑转发已恢复／清理。原始 XML、日志、截图、设备标识、媒体地址和签名私钥不随案例发布。
