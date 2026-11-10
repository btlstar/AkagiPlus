# RiichiCityStyle · 麻雀一番街本地装扮

在游戏原有界面选择角色、皮肤、头像、称号和装备，保存装扮方案与星标。补丁保留真实养成数值；头像、语音及随机方案的覆盖范围有限。

独立图形管理工具见 [RiichiCityStyle](https://github.com/btlstar/RiichiCityStyle)，与本目录使用同一装扮核心。独立装扮无需代理；下述 Proxifier 用于 AkagiPlus 的一番街 AI 捕获。

## 使用

日常打开 AkagiPlus，在总览选择一番街并点击「启动游戏」，保留 Proxifier。装扮页提供安装/更新、还原与状态检查。游戏运行时禁止安装或还原。

生成补丁需要 `requirements.txt` 中固定版本的 UnityPy。可使用项目 Python，或在私人文件 `.local/riichicity-local-python.txt` 填写独立解释器路径；还原只需 Python 标准库。

只有一个游戏文件会被替换：`Mahjong-JP_Data/StreamingAssets/Base/lua_network`。安装器拒绝未知客户端更新或热更新覆盖；已知旧补丁可安全升级。GUI 的原始文件、暂存包和恢复记录放在当前用户 `AppData/Roaming/akagiplus/riichicity-local`；源码命令行旧记录保留在忽略提交的 `.local/`，不分发游戏资源。

游戏自带「安全模式」若包含自己，会在进入牌桌时将自身皮肤切回默认；要显示特殊皮肤，应关闭安全模式对自己的处理。它不影响候场和资料详情页，因此这两处正常不代表牌桌也会显示。补丁保留游戏原有的显示设置。

选择按账号存入 Unity PlayerPrefs；升级保留已有选择。补丁只处理本机外观，不修改抽卡、购买、奖励或对局牌和点数，也不改变外部 RiichiCityUnlock 授权模式。复杂随机方案仍待完整适配，目前使用指定项。

新增代码沿用项目 Apache-2.0 许可；可选依赖 UnityPy 使用 MIT 许可。仓库不包含 UnityPy 或游戏资源。
