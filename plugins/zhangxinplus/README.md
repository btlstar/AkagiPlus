# ZhangxinPlus · 掌心 Plus

掌心全民麻将本地装扮插件，版本见 [plugin.toml](plugin.toml)，资源兼容性由安装器核验。AkagiPlus 提供安装、还原和游戏启动入口；插件运行不依赖 AkagiPlus 代理或 Proxifier。

## 使用

1. 正常启动掌心，完成官方资源更新后退出。
2. 在 AkagiPlus 总览或设置中选择「掌心全民麻将」，在「装扮」页安装 / 更新 ZhangxinPlus。
3. 使用 GUI 的游戏启动按钮。在游戏原有界面选择装扮，插件按游戏账号将选择保存在本机。
4. 需要停用时，退出掌心并在装扮页还原游戏文件。本地选择会保留。

已接入角色、皮肤、星标、桌布、牌背、麻将牌、立直棒、特效、表情物品、音乐、称号、头像框与牌桌边框。自身友人房卡片和牌桌资料会应用本地选择，其他玩家的资料保持原样。

支持装扮方案的新增、保存、使用、改名与删除，兼容数字和文本形式的方案 ID。觉醒表情在本机显示解锁，真实好感度及觉醒进度保留。头像与语音尚未完整适配。

普通立直 AI 支持友人局三麻、四麻，其他玩法未开放。插件只改变本机显示，不改变服务器拥有物、货币、赠礼、抽取或养成。

## 独立管理

需要独立图形管理窗口时，下载 [ZhangxinPlus](https://github.com/btlstar/ZhangxinPlus)。

Python 需要 UnityPy 1.25.4；AkagiPlus 附带的 runtime Python 已包含依赖。在仓库根目录运行：

```powershell
$py = "runtime/python/x86_64-pc-windows-msvc/python.exe"
$game = "D:/Program Files (x86)/zhangxinmajiang"
$state = "$env:APPDATA/akagiplus/zhangxinplus"
& $py plugins/zhangxinplus/manage.py install $game --state-dir $state
& $py plugins/zhangxinplus/manage.py status $game --state-dir $state
& $py plugins/zhangxinplus/manage.py restore $game --state-dir $state
```

`--state-dir` 应保持一致；上例与 AkagiPlus GUI 共用安装记录。省略时使用 `%LOCALAPPDATA%/ZhangxinPlus`，适用于独立发布。

安装会检查已适配的资源版本、原始哈希及当前文件，先备份再替换两个 Lua 资源包；更新时从已核验的原始备份重新构建。未知更新或备份损坏会停止覆盖。保留所用 state 目录，直到完成还原。不修改官方版本索引或跳过更新检查。

源码和分发包只包含本插件，不包含游戏资源、研究副本或私人资料。许可见 LICENSE.txt（Apache-2.0）。

## 普通立直 AI 预览

在 AkagiPlus 的「机器人」页配置四麻 / 三麻 AI，选择掌心平台并启动捕获，然后在一场新对局开始前进入游戏。建议显示于「对局」页或 AkagiPlus 悬浮窗；目前不提供自动操作。

客户端在消息解码后，只把白名单对局事件写入本机队列，AkagiPlus 转为 mjai 并送入原有 AI 引擎。无需 Proxifier、MITM 或证书。账号登录凭据和聊天不写入此队列；启用采集需要 AkagiPlus 定期续期的短期本机开关，程序退出或停止后失效。插件可以独立使用装扮功能。

首版要求普通立直玩法、明确的三 / 四人座次及完整开局资料。中途加入、消息中断或未知特殊玩法会暂停 AI，等待下一场重新连接，不尝试猜测手牌。队列有轮换限制，只留在本机游戏目录；本机日志记录转换后的 mjai。
