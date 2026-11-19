# Marco Movie TV 安装与片源配置

Marco Movie TV 可直接读取用户有权访问的 AppleCMS JSON 点播接口，作为独立于 LibreTV 后端的观影入口。首页推荐、电影和剧集分类及可播线路取决于所导入的片源。[Marco Movie 项目说明](https://github.com/Pilipala9919/MarcoMovie)

## 安装电视版

1. 用只读快照确认目标电视、Android SDK 版本、ABI 和已安装的包。从项目发布页找 `android-tv-v*` 标签，选择文件名以 `-android-tv.apk` 结尾的电视包。项目按平台分别发版，GitHub 标记的 Latest 可能指向其他平台。[Marco Movie 发布页](https://github.com/Pilipala9919/MarcoMovie/releases)
2. 将下载文件的路径赋给 `MARCO_APK`。用 SDK build-tools 核对包名、最低 SDK、ABI 和签名，并将 SHA-256 与该发布的摘要比较。Linux 可用 `sha256sum` 计算摘要。原位升级时另核对已安装应用的签名，匹配后用 `install -r` 保留应用数据。[应用安装与兼容性检查](apps-and-ui.md#来源和兼容性)

   ```sh
   aapt2 dump badging "$MARCO_APK"
   apksigner verify --print-certs "$MARCO_APK"
   shasum -a 256 "$MARCO_APK"
   ```

3. 首次安装时运行下面的命令。安装成功后也可从 Tigris 的应用列表打开「Marco Movie」。此例的包名和入口取自实测电视版，其他版本先检查 APK 的电视入口。

   ```sh
   adb -s "$TV_SERIAL" install "$MARCO_APK" &&
     adb -s "$TV_SERIAL" shell am start -n com.pilipala.marcomovie/.MainActivity
   ```

## 导入已有片源

1. 准备用于点播的原始 AppleCMS JSON 接口。若片源已经在 DpadTV 使用，从它的「片源」页辨认该接口，也可从自己的媒体后台取得。示例地址为 `https://video.example.com/api.php/provide/vod/`。直接填写点播接口本身即可，LibreTV 网站首页和演示站地址用于其原有连接方式。
2. 在 Marco Movie TV 首页依次选择「导入我的配置」→「遥控输入」，将地址填入「导入配置」的输入框，选「导入地址」。长地址也可用同网手机扫描应用显示的二维码，通过导入页提交。配置地址、凭据和观看记录留在本地。[上游电视端导入说明](https://github.com/Pilipala9919/MarcoMovie/blob/android-tv-v0.5.23/docs/USER_GUIDE.md)
3. 回到「发现」，确认片源名称和「推荐」海报墙，再切到电影、剧集分类。如果首页为空，先核对接口是否返回带 `list` 的 AppleCMS JSON，分类通常由 `class` 字段提供。片单能加载但个别影片报错时，另查选中的播放线路和媒体可达性。
4. 用现有界面取证脚本检查实际前台、分类与影片详情。点播后观察进度增长、解码和音轨，正常退出再重开应用，确认片库仍能加载且可以续播。硬件解码画面可能无法截屏，电视前的用户可确认实际画面和声音。[界面与播放验证](apps-and-ui.md#ui-与播放判断)

## 更新失败与现有源失效

### 官方电视版原位升级

先从电视读取实际版本。应用出现更新提示后，再核对安装后的 `versionName` 和 `versionCode`。本次原机仍为 0.5.23，随后使用官方电视版 APK 完成升级。

更新镜像无法访问时，从项目官方对应电视标签取得 APK。退出播放器，保存原安装包与可导出的配置、观看记录及收藏，再校验新 APK 的摘要、最低 Android 版本、ABI 和签名。签名一致后用 `adb install -r` 原位安装，安装后读回版本并重开应用。[应用安装与备份](apps-and-ui.md)

本次验证的官方电视版为 0.5.26，`versionCode=90`、最低 API 23，包含 `armeabi-v7a`。APK SHA-256 为 `35289520db05bc0f0484915f16a7f87cdc2d019409da6b976298c5486a79e523`，证书 SHA-256 为 `2549f01e89c41201ea171847048228c6df79a7c57fff2ec9a439195c757a80de`。后续发布按当次产物重新核对。[官方电视版 0.5.26](https://github.com/Pilipala9919/MarcoMovie/releases/tag/android-tv-v0.5.26)

### 编辑已有片源地址

在 0.5.26 的「片库」打开当前片源名称，选中现有线路后按遥控器菜单键，进入「编辑线路信息」。在「接口地址 / Spider API」填入已在电视端验证的同站备用接口，选择「保存修改」。输入法遮住按钮时先收起输入法，再核对保存后的页面。

在已有线路上修改地址可以保留线路身份。保存后检查首页、分类、搜索、详情和播放，再正常退出并重新打开应用，确认选中的线路及接口仍生效。备用地址的验证方法见[片库为空的连接排查](libretv-repair.md#本机服务正常但片库为空)。

### 电视缺少文件选择器时备份

支持导出文件的电视可在 Marco 的设置中使用「备份配置与偏好」。本次电视缺少系统文件选择器，采用应用自带的「同步 → 本机局域网接收码」。该短时页面的 `/sync` 支持只读 GET，可导出观看记录、收藏和允许同步的订阅源。取得当前页面显示的临时地址后，备份到本地私有目录，完成后关闭接收页面。

该导出的内容范围为可同步数据。额外的播放偏好、插件登录状态或隐私空间按应用实际提供的功能单独处理。

## 红米 A50 2025 真机案例（2026-11-14）

- MiTV-ASTP0，HyperOS OS3.0.11.0.PSTAATV，Android 9／API 28，`armeabi-v7a`。已安装 `MarcoMovie-0.5.23-android-tv.apk`，最低 API 23，包名 `com.pilipala.marcomovie`，签名校验通过且 SHA-256 与上游一致。[电视版 0.5.23 发布页](https://github.com/Pilipala9919/MarcoMovie/releases/tag/android-tv-v0.5.23)
- 用遥控输入导入同一台电视上已有的 AppleCMS 片源，看到推荐及电影、剧集分类。样片进度持续增长，设备记录到 1920×1080 H.264 硬解帧数增加与 AAC 音轨输出，重开应用后从已保存进度续播。验证范围为这台电视、该版本和一个点播片源。其他设备和片源按上述流程试播。

## 红米 A50 2025 真机案例（2026-11-19）

同一台电视已升级至 HyperOS OS3.0.102.0.PSTAATV，Android API 为 28。Marco 从官方电视版 0.5.23 原位升级至 0.5.26，安装前后证书一致。原片源域名在电视端连接超时，随后在现有线路中修改为同一提供方的备用接口。

升级后片库、分类和搜索恢复，实际搜索返回 20 条结果。测试影片以 1920×800 H.264、25 fps 硬解播放，已记录到 AAC 音轨；观察时解码帧数从 2327 增加到 2720，丢帧与解码错误计数为零。用户确认画面与声音正常。退出后保存测试续播进度，重新打开应用并再次搜索，片库和配置通过核对。

通过应用自带的局域网只读导出比较升级前后数据，原观看记录各字段一致，收藏及原订阅身份一致，测试新增一条观看记录。相关的 DpadTV 修复、验证范围及更新方式见[本次更新记录](../updates/2026-11-19.md)。
