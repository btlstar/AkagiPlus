AkagiPlus @VERSION@ — Windows x64

完整解压后双击 AkagiPlus.exe，保留 runtime、plugins 等相邻目录。
在「总览」选择游戏并点击「启动游戏」；运行后可点击「返回游戏」。
在「机器人」配置 AI；新对局开局前连接，建议显示在「对局」或悬浮窗。

Archer：在「机器人」打开 Archer 插件配置，填写自己的密钥并分别选择三麻、四麻模型。
在「机器人」页的 Archer API 卡片获取模型并检查连接。API Token 由 Archer 另外计费。
若机器人列表提示环境未安装，先点击安装环境。为三麻、四麻同时选择 Archer 后按新对局人数自动切换；候选百分比表示相对权重，不是胜率。
局前连接检测不调用付费推理；局中不显示 Token 用量。
雀魂：在「装扮」启用 MajsoulMax-rs，使用 MITM 与专用浏览器。
麻雀一番街：选择 Game/Mahjong-JP.exe，AI 捕获需配置并保持 Proxifier 运行。
RiichiCityStyle 装扮在「装扮」页安装、更新和还原；仅装扮无需代理。
掌心全民麻将：完成官方更新并退出游戏后，在「装扮」安装 ZhangxinPlus。
掌心资源兼容性由安装器检查，普通立直友人局支持三麻、四麻 AI，无需代理或证书。
天月麻雀：选择 mahjongP.exe，AmatsukiStyle 默认启用，登录后恢复本地大厅装扮。
天月通过本地消息提供普通立直 AI，无需代理或证书，客户端重启后自动重新连接。
天凤：保留原有浏览器启动、捕获与 AI 功能。

天月与掌心的特殊玩法、中途恢复和自动操作暂不支持。
掌心头像和语音尚未完整适配。装扮与 AI 的具体范围见对应插件使用说明。
独立工具与内置装扮无需重复启用；恢复时保留与游戏目录匹配的备份。
独立装扮项目：
RiichiCityStyle：https://github.com/btlstar/RiichiCityStyle
ZhangxinPlus：https://github.com/btlstar/ZhangxinPlus
AmatsukiStyle：https://github.com/btlstar/AmatsukiStyle
系统要求：Windows x64、WebView2；无需另装 Python 或 Node。
发布包不含个人配置、密钥、登录资料、证书、日志、游戏客户端或游戏资源。
本地装扮不增加服务器拥有物，也不改变真实购买、奖励和养成进度。

更新前退出游戏与程序，备份个人设置，使用完整包更新。
旧版为便携配置时，备份并迁移 configs/config.toml、mjai_bot/archer-api/settings.toml、
.local/majsoulmax 和已有 mjai_bot 插件；不要覆盖新版程序文件。
使用用户目录配置时保留 %APPDATA%/akagiplus。不要分享个人密钥或证书。
保留用户目录 akagiplus/riichicity-local 与 akagiplus/zhangxinplus 中的原始恢复备份。
天月本地装扮选择位于 %LOCALAPPDATA%/AmatsukiStyle/profiles。
版本：v@VERSION@，基于 Akagi 3.9.0。
下载：https://github.com/btlstar/AkagiPlus/releases/tag/v@VERSION@
许可见 LICENSE.txt、NOTICE、LICENSES；MajsoulMax 源码及 GPL 许可随包提供。
