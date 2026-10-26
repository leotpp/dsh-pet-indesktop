# Magpie 额度轮播（2026-10-26）

基线：`34d810b1`；本地 macOS Apple Silicon，Python 3.13.11、PySide6 6.12.0。
本报告补充 [设置变更门禁](SETTINGS-CHANGE-GATES.md) 与 [代理策略](NETWORK-PROXY-AND-VPN-2026-09-22.md)，用户入口见 [README](../README.md#magpie-额度轮播)。

## 核心特性

灵动岛既有 `dynamic_island.info_mode` 新增 `magpie` 取值（默认仍为 `time`），在既有选择器中显示“Magpie 额度轮播”。每 5 秒切换一个额度窗口，每分钟读取本机 Magpie 缓存。账户各窗口的剩余百分比、无窗口的余额和错误条目分别呈现；完整列表与重置时间在悬停提示中保留。隐藏、关闭信息栏、切换模式、关闭窗口和退出应用均停止查询、取消在途响应并清理旧提示。

本机端点固定为 `http://127.0.0.1:3425/v1/magpie/quotas?kept=1`，直连、禁止重定向、3 秒网络超时、响应上限 1 MiB。不读取供应商凭据、不调用模型，不请求 `/refresh`。缓存新鲜度由 Magpie 管理。

## 修改文件说明

- `pet/island/magpie.py`（新增）：验证/格式化接口响应，Qt 异步请求、轮播与生命周期；同一批文本和字体只测宽一次。
- `pet/island/dynamic_island.py`：按可见性和信息栏模式启停，接入主信息段和安全转义后的完整提示；保留现有 DeepSeek 余额链路。
- `pet/config.py`：既有枚举接受 `magpie`；没有新增持久化键，旧配置无需迁移，旧版读取该取值时回落 `time`。
- `pet/modern_settings_dialog.py`：原选择器新增一个选项，说明刷新和悬停行为；原保存、模块门控及搜索归属不变。
- `tests/test_magpie_allowances.py`（新增）：响应边界、余额/窗口/错误、真实回环 HTTP、轮播/停止/失败清旧值、配置往返/设置选项、长文本宽度及提示生命周期。
- `tests/test_architecture.py`：设置对话框预算实测 +1 行，仅用于选择器新增项。
- `README.md`、`docs/INDEX.md`、本报告：用户入口、限制和验证记录。

增删行数（`git diff --numstat`；新增文件按实际行数）：

| 文件 | 增 / 删 |
|---|---|
| `pet/island/magpie.py`（新增） | +170 / −0 |
| `pet/island/dynamic_island.py` | +36 / −0 |
| `pet/config.py` | +2 / −2 |
| `pet/modern_settings_dialog.py` | +2 / −1 |
| `tests/test_magpie_allowances.py`（新增） | +253 / −0 |
| `tests/test_architecture.py` | +1 / −1 |
| `README.md` | +6 / −0 |
| `docs/INDEX.md` | +3 / −1 |
| 本报告（新增） | +78 / −0 |

没有删除文件。

## 性能分析

命令：`.venv/bin/python .scratch/magpie/perf.py`（本机隔离配置、真实缓存 GET；本地取证脚本与日志不提交）。同机四分片测试运行期间采样，非跨平台结论。

- 三次缓存 GET：59.22 / 3.96 / 3.94 ms；9 个展示条目。
- 格式化响应 1000 次：30.48 µs/次；一次请求成功后处理一次。
- Magpie 主信息段 1000 次：2.04 µs/次；同场时间模式 4.40 µs/次。
- 初版每次重测所有长文本为 500.92 µs/次；现按文本批次/字体度量缓存，轮播只选缓存项。
- 预热 100 次后再格式化 1000 次，Python 堆保留增量 655 字节、峰值 7307 字节；这是短期格式化探针，不代表完整应用长期内存。
- 新路径有每分钟一次本机 HTTP 请求、两个 Qt 定时器（查询 60 秒、轮播 5 秒）；使用 Qt 网络管理器，不新建 Python 工作线程、不写额度缓存或凭据。Qt 内部网络线程由 Qt 管理。未激活模式不创建该服务；隐藏/关闭后停表并中止请求。缓存大小受 1 MiB 响应上限约束。

## 实机运行记录

命令：`.venv/bin/python .scratch/magpie/probe.py`；真实 `cocoa` 插件，临时配置，连接正在运行的 Magpie。日志、两张窗口截图保存在 `.scratch/magpie/`，含个人额度、不提交。

```json
{"platform":"macOS-27.2-arm64-arm-64bit-Mach-O","qt":"6.12.0","plugin":"cocoa","first_ms":330.75,"rows":9,"first_index":0,"width":448,"next_index":1,"next_width":448,"visible":true,"hidden_stops":true}
```

实际 5 秒定时器从第 1 项切到第 2 项，胶囊宽度保持 448 逻辑像素；真实窗口截图已人工检查。第一次探针发现省略后的测宽顺序导致 2px 抖动，已以合成回归复现 `[447,449,449]` 后修正，并用上述 Cocoa 探针复验。关闭 Magpie/网络 HTTP 错误通过独立本机 HTTP 服务验证，没有为了测试停止用户 Magpie。Windows/Linux 未做实机验证。

另外执行 `.venv/bin/python .scratch/magpie/settings-probe.py`，真实 Cocoa 下 1100px 和 720px 两档设置页均能显示 Magpie 选项；行尺寸分别为 798×100、452×130，说明文字高度 30/60px，截图已检查无裁切。

本机已从新源码启动（进程 66452），系统枚举得到 44px 高的灵动岛与宠物合成窗两个在屏窗口。`启动桌宠.command` 和忽略的 `packaging/build_variant.py` 为本机启动产物，继续使用 `webm-chat` 配置目录；启动前保存完整备份 `config.before-magpie.json`，仅启用灵动岛并将信息栏改为 `magpie`。现有帧序列以 APFS clone 复制供源码使用；原安装包可回退。独立 Qt 探针能用 `QWidget.grab()` 截图；系统 `screencapture -l` 捕获已启动应用窗口返回 `could not create image from window`，未申请额外录屏权限，故不声称拿到了该进程的系统截图。

## 测试与验证

- 接线前配置与显示回归：`2 failed, 12 passed`（旧配置丢失 `magpie`，主栏没有额度）。
- 新功能聚焦：22 passed。
- 新功能与收缩/内容缓存相关族：57 passed。
- 早期配置/架构/灵动岛/功能门控相关族：226 passed、2 skipped。
- `ruff check pet/ tests/`：通过。
- 最终配置/架构/额度/FPS 退出/交付文档相关族：366 passed。
- CPU 负载复跑：12 个 CPU 工作进程下，新增 22 项测试连续三轮均通过（`.scratch/magpie/load.py`）。
- 全量按文件均分四进程：最终累计 **9011 passed / 83 skipped / 3 failed**。初轮有一项本改动引入的退出钩子计数失败，已将新钩子延迟到 Magpie 激活后注册；所属完整分片重跑 **2934 passed / 10 skipped**，其余三片为 2014 / 2099 / 1964 passed。
- 剩余三项：`test_library_shared_media.py` 的两个共享解码用例，以及 `test_windows_node_env.py::TestConfiguredPnpmBin::test_broken_config_falls_back_to_discovery`。在 `34d810b1` 干净 worktree 上按相同分片顺序复现媒体两项失败（2014 passed / 22 skipped / 2 failed），pnpm 用例单独复现，读到了本机真实 nvm 路径。与本次改动无关，未扩大范围修复。全量没有宣称全绿。
- `git diff --check`：通过。最终 ruff 复验通过。

## 已知限制与恢复

仅连接默认本机端口；未开放自定义地址/密钥。访问受限时如实提示。读取 Magpie 缓存，数值不比 Magpie 本身更新更快；不自动登录账户、不发语音。长行在胶囊内省略，完整内容可悬停查看。切回“当前时间”即停止该功能；原安装包需运行含本改动的源码或重新构建才能提供新选项。
