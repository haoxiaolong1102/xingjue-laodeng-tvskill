# 保留全部功能的后台优化

## 先判断是不是真的缺内存

比较同一场景下多次 `/proc/meminfo` 的 `MemAvailable`、`dumpsys meminfo` 中 PSS 与进程重启、`dumpsys cpuinfo` 的 CPU、可用存储和实际交互。缓存可回收，低 MemFree 不等于卡顿。
在案例约 1.96 GiB RAM 的设备上，初始 MemAvailable 约 951 MiB，存储用量约 21%，不能诊断为内存耗尽。

四核设备某语音进程占 35% of one core，不能写成占整机 35%。完整性能判断需要相同采样区间、CPU 核数、持续活动、解码／动画场景，不拿单张 top 读数承诺收益。

## 该案例实际做了什么

- 关闭已查明的 OEM 相册定时路径，回到静态 Home。Tigris 动态相框的 Ken Burns 动画比静态 Home 更耗 CPU，不能据此禁用所有相册功能。
- Tigris 设置中关闭“待机时清理”，周期清理设为关闭／0，保留手动入口。该版默认 `clean_on_standby=true`、`clean_interval=4h`，使用当前设置 UI，修改前记原值。
- 不启用 self-ADB 清理授权，不安装常驻内存清理器。
- 语音唤醒、AirPlay／DLNA、HDMI、遥控器、网络、播放器与原厂桌面保持。不要为了 MemFree 数字 force-stop 全后台。

案例静置窗口里 Home CPU 平均约 0.025% of one core，MemAvailable 约 867–888 MiB；语音唤醒约 35.82% of one core，按“全功能”要求保留。这是场景观察，不是承诺优化固定释放多少内存，也不能用修改前不同场景的 951 MiB 与此直接做收益差值。

## TVManager 的两条路径

TVManager 2.7.49 日志显示：

1. 独立“内存自动清理”开关为 off：`isMemoryAutocleanSwitchOn ... return false`，`switch off,clean ignore`。
2. 另一条 `startapps_completed_boost` → `OPERATION_REQUEST_BOOST_SILENCE` → `ShortcutBoostService` 发起清理，投屏服务被杀后又重启。

共享 receiver 同时处理手动加速／天气，service 也可能被手动操作使用；原机 APK 的目标实现未能从 DEX 验证，未找到可靠独立开关，所以**保留组件**。日志时间相近不足以证明相册触发清理。关闭 Tigris 的清理选项也不是“修好了 TVManager”的证据。

## 不采用的通用“优化”

不根据网上黑名单批量 disable／uninstall；不改 ZRAM、LMK、low-RAM 标记、开发者后台进程上限、SurfaceFlinger 或 GPU 属性；不禁用整套 TVManager／原厂 launcher；不批量清应用数据。用户请求单项取舍时才检查该项依赖，单独记录并验证。

使用同样场景回测 Home 响应、真实静置、播放、语音、投屏与 HDMI。包名仍存在、PID 没变化只说明部分状态；不能代替用户实际操作验证。说明仍未解决的 CPU 消耗及保留它的功能原因，不编造更大的“深度优化”数字。
