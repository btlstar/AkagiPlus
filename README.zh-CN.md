# AkagiPlus

基于 [Akagi 3.8.0](https://github.com/shinkuan/Akagi) 的麻将 AI 与本地装扮扩展。提供统一游戏启动入口，集成雀魂 MajsoulMax、一番街本地装扮和掌心 ZhangxinPlus。

[English](README.md) · [繁體中文](README.zh-TW.md) · [下载预发布版](https://github.com/btlstar/AkagiPlus/releases/tag/v3.8.0-plus.2)

## 界面预览

AkagiPlus 截图使用当前界面与演示配置，不含账号或密钥。掌心界面由用户实测提供。

![总览：选择平台与启动游戏](docs/images/overview.png)
![装扮：掌心插件安装、更新与还原](docs/images/cosmetics.png)
![对局：模块化牌桌与 AI 建议入口](docs/images/game.png)
![掌心：游戏原有装扮与方案界面](docs/images/zhangxin-cosmetics.png)

## 下载与启动

从 [Releases](https://github.com/btlstar/AkagiPlus/releases/tag/v3.8.0-plus.2) 下载 `AkagiPlus-3.8.0-plus.2-windows-x64.zip`，完整解压后双击 `AkagiPlus.exe`。保留旁边的 `runtime`、`plugins` 等目录。

本版为 Windows x64 便携预发布包，需要 WebView2；无需另外安装 Python 或 Node。AI 服务密钥和模型由用户配置，发布包使用空白默认配置。

1. 在「总览」选择游戏，点击「启动游戏」；运行后可点击「返回游戏」。
2. 在「装扮」中启用或安装对应插件；安装、更新及还原前先退出游戏。
3. 在「机器人」配置四麻、三麻 AI，在新对局开始前连接；建议显示在「对局」或悬浮窗。
4. 「重启捕获」用于连接维护；日常启动使用游戏启动按钮。

## 支持范围

| 平台 | 启动与 AI | 本地装扮 |
|---|---|---|
| 雀魂 | 专用浏览器，保留上游捕获与 AI | MajsoulMax，在游戏原有界面换装；启用时使用 MITM |
| 麻雀一番街 | Windows 独立客户端与 MITM，需自行配置 Proxifier | 角色、皮肤、头像、称号、星标、装扮方案 |
| 掌心麻将 | Windows 客户端，本地消息通道；友人局普通立直三麻、四麻已实测 | ZhangxinPlus 0.1.5；角色、皮肤、特效、桌布、牌背、麻将牌、立直棒、表情、音乐、称号、头像框与方案 |
| 天凤 | 保留上游启动、捕获和 AI | 本版没有新增装扮插件 |

天月麻将尚未接入：上游 v2 有历史协议桥，v3 仍列为计划中。装扮与 AI 接入的证据和待验证项见[天月调查](docs/AMATSUKI_FEASIBILITY.md)。

掌心无需代理或证书，目前适配资源 **92217**。特殊玩法、中途恢复和自动操作尚未支持；头像与语音未完整适配。详见 [ZhangxinPlus](plugins/zhangxinplus/README.md)。

一番街选择 `Game/Mahjong-JP.exe`，并保持 Proxifier 运行。进桌后特殊皮肤变成默认皮肤时，请检查游戏「安全模式」是否包含自己。详见[一番街说明](docs/RIICHICITY.md)。

插件先核验资源并备份原文件，未知更新会拒绝覆盖，可在「装扮」页还原。本地换装不改变服务器拥有物、货币、奖励或养成进度，也不保证其他玩家视角可见。

## 配置与更新

- 更新请下载完整包，先退出游戏和 AkagiPlus，并备份个人配置。
- 发布包不含密钥、个人设置、登录资料、日志、证书或游戏资源；首次使用后在本机生成资料。
- 恢复记录位于用户配置目录的 `riichicity-local` / `zhangxinplus`，请保留原始资源备份。
- 版本按实际合入的上游基线加 Plus 修订号：`v3.8.0-plus.2`；同步新上游后再更新基线版本。
- 更新检查仅访问本分支。预发布版也可在 Releases 页面手动下载。

## 开发与许可

源码使用 `start.bat` 开发启动，发布版直接运行 EXE，游戏入口均在 GUI 中。[开发说明](docs/AKAGIPLUS.md) · [发布构建](docs/RELEASE.md) · [验证范围](docs/VALIDATION.md)。

Akagi 主体与自编写 ZhangxinPlus 保留 Apache-2.0；MajsoulMax 改编部分保留 GPL-3.0，并随包提供对应源码、许可和[来源记录](plugins/majsoulmax/PROVENANCE.md)。详见 LICENSE.txt、NOTICE、LICENSES。一番街可选外部 RiichiCityUnlock、Proxifier 及游戏客户端不随包提供。
