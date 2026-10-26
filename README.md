# macOS 桌宠 · Magpie 额度查看

这是基于 [MerZlin/dsh-pet-indesktop](https://github.com/MerZlin/dsh-pet-indesktop) 的个人自用分支。

**本人日常使用 macOS，因此这个 fork 主要围绕 macOS 使用体验维护。** 当前重点是把本机 **Magpie（麦克派）的 allowance / 剩余额度**放在桌面上查看，不用反复打开 Magpie。

## 当前功能

- **Magpie 额度轮播**：在灵动岛中轮流展示各账户、各额度窗口的剩余百分比，以及接口提供的余额和重置时间。
- **自动更新**：每 5 秒切换一项，每分钟读取一次 Magpie 缓存；鼠标悬停可查看完整列表。
- **桌宠陪伴**：动画、拖拽、角色切换与右键菜单。
- **按需开启功能**：保留天气、AI 对话等原项目能力，可在设置中选择使用。
- **隐藏 Dock 图标**：可关闭 Dock 中源码运行时的 Python 图标，继续通过宠物右键或顶部托盘操作。

## Magpie 额度轮播

1. 在 Mac 上启动 Magpie，使用默认本机端口 `3425`。
2. 打开桌宠设置，在「功能」中启用「灵动岛」；首次激活模块需要重启桌宠。
3. 进入「桌面组件 → 灵动岛」，开启信息栏。
4. 将「信息栏显示什么」选为 **Magpie 额度轮播**。

桌宠只读取 Magpie 的本机缓存，不调用模型、不消耗模型额度，也不需要填写供应商 API Key。数据的新鲜度由 Magpie 管理；读取失败时会显示提示。

## 在 macOS 上运行

需要 Python 3.10 或更高版本，建议使用 Python 3.13。

```bash
git clone https://github.com/leotpp/dsh-pet-indesktop.git
cd dsh-pet-indesktop
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m pet
```

已经配置好本地启动入口时，也可以直接双击 `启动桌宠.command`。该文件是本机启动文件，不随仓库分发。

本 fork 的额度轮播需要运行这里的源码或包含这些改动的构建；上游安装包不会自动获得本 fork 的新功能。

## 日常使用

- **打开设置或退出桌宠**：右键桌面上的宠物，或使用顶部托盘菜单。
- **隐藏 Python 图标**：在设置中关闭「显示 Dock 图标」，保存后生效，下次启动仍保持。
- **使用 AI 对话**：在「设置 → AI 与对话」中配置服务，点击侧栏「保存并退出」。
- **查询天气**：启用天气模块并重启后，右键宠物选择「查看天气」。

更详细的安装、功能与进阶配置见 [完整使用指南](USER-GUIDE.md)，开发资料见 [文档索引](docs/INDEX.md)。

## 来源与许可

感谢原项目 [MerZlin/dsh-pet-indesktop](https://github.com/MerZlin/dsh-pet-indesktop) 的桌宠实现，以及 [Magpie](https://github.com/yetone/magpie) 提供的本机额度接口。

代码遵循 [MIT License](LICENSE)。动画、音效及其他第三方素材的来源和许可见 [第三方声明](THIRD_PARTY_NOTICES.md)。
