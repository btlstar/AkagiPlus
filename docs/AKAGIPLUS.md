# AkagiPlus 开发说明

本分支基于 Akagi v3.8.0（63cea4b5d23d83bbee8d56bc3b9d547cca2046c3）。已增加雀魂 MajsoulMax，并新增一番街 RiichiCityUnlock 外部插件接入。外部插件保留原文件夹和配置，不包含它的二进制或源码；另提供直接使用游戏界面的一番街本地装扮补丁。

## 掌心麻将（开发预览）

在总览选择掌心，在装扮页安装 ZhangxinPlus 0.1.5；机器人页配置 AI 后，从 GUI 启动掌心，在一场新对局开局前连接。使用本地解码消息通道，免代理、免证书。友人局普通立直三 / 四麻 AI 已通过用户实测，建议通过 AkagiPlus 对局页及悬浮窗展示，特殊玩法、自动操作及中途对局恢复暂不开放。真实对局结果由用户手动验收。详见 [ZhangxinPlus](../plugins/zhangxinplus/README.md)。

## 本次功能

- 侧边栏新增「装扮」，可启用 MajsoulMax、查看模块状态与已处理装扮消息数量。
- 使用原 Akagi 的 MITM 捕获；先将原始数据交给 AI 协议桥，再进行本机装扮处理。
- Python 装扮模块采用独立 JSONL 进程，按 WebSocket 连接维护请求编号，注入通知只发给对应游戏客户端。
- 登录及角色/装扮列表使用配套协议与资源快照；在游戏内更换皮肤后，选择保存到私人目录。
- 保留 CopilotPlus 的友人房修复：本人角色 ID、皮肤及头像一致，覆盖创建/加入/获取房间及房间成员更新；未知字段与其他玩家数据保留。
- 处理失败/超时暂停 MajsoulMax 并显示提示，原始流量及 AI 捕获继续。此时应停止捕获后重新启动并重新登录，以恢复一致的装扮状态。
- 装扮扩展默认关闭；不会自动迁移旧项目的登录、API 密钥或装扮选择。
- 雀士星标保存在本机。宿舍隐藏名单保存方案经用户实测未生效，已移除本次尝试；暂不支持跨重启保持隐藏名单。
- 专用雀魂浏览器隐藏命令行参数与缺少 Google API Key 的启动提示，仍使用原有本机 CA 公钥固定。
- 一番街原生客户端启动与路径设置见 [RIICHICITY.md](RIICHICITY.md)。
- AkagiPlus 使用独立应用标识；源码启动配置为 `.local/config.toml`，装扮选择位于 `.local/majsoulmax/settings.mod.yaml`，专用浏览器资料位于 `.local/browser`。这些文件均忽略提交。
- 应用仅检查 AkagiPlus 发布；便携版下载完整压缩包手动更新，源码开发继续使用 Git。打包/发布工作流的上游副本保留作来源参考，不自动上传产物。

打开游戏的简明步骤见 [START_GAME.md](START_GAME.md)。

## 开发环境与启动

需要 Rust stable MSVC、微软 C++ Build Tools/Windows SDK、Node.js（满足上游 Vite 8 要求）、protoc、CMake，以及 Python 3.11+。原 Akagi 的可选 Python AI 机器人另需 uv；MajsoulMax 本身不依赖 uv 或 PyTorch。

首次准备（已有工具时执行）：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r plugins/majsoulmax/requirements.txt
.\.venv\Scripts\python.exe scripts/setup-protoc.py
cd frontend
npm ci
cd ..
```

`start.bat` 启动 Tauri 开发模式，按需编译 Rust 并启动 Vite。它不自动安装系统工具，也不生成发布包。首次编译 Akagi 原有依赖仍可能较慢，fork 不会消除这部分构建成本。当前机器可使用上一轮放在 `D:\DevTools` 的工具；其他位置可通过 `AKAGIPLUS_DEVTOOLS` 指定，或者直接将工具加入 PATH。

1. 运行 `start.bat`，完成原 Akagi 初始化；保持自动操作关闭。
2. 平台选择雀魂，进入「装扮」，开启 MajsoulMax 并保存。保存会重启捕获，不要在对局中修改。
3. 在「总览」点击「启动游戏」。这个入口使用系统 Chrome/Edge 的独立资料目录与本机 MITM 代理，并仅接受本项目 CA 公钥；不安装系统根证书、不改系统代理。
4. 重新登录，在游戏内选择装扮。关闭 MajsoulMax 后同样需要重新登录恢复原始数据。
5. AI 仍在原 Akagi「机器人」页面配置。本次没有复制个人密钥，也没有更改原 Akagi 的模型选择、单合法动作处理或云端失败时的本地回退行为。

专用浏览器读取 `.local/config.toml` 中的代理地址及 CA 目录，不预置 7897 等上游端口。使用非默认浏览器时设置 `AKAGIPLUS_BROWSER` 为浏览器 exe 路径。TUN 路由仍由外部客户端控制。

## 验证

按[开发验证指南](VALIDATION.md)只运行受影响的检查。完整构建用于构建相关改动或发布前检查，不是每次装扮 Lua/文档修改的固定步骤。

## 同步上游

`origin` 是 btlstar/AkagiPlus，`upstream` 是 shinkuan/Akagi。后续在本分支先提交自己的工作，再 fetch upstream 并合并其 v3 更新，解决冲突后按受影响范围验证，发布前再做完整构建。不要用上游二进制替换本分支。

MajsoulMax 的算法逻辑与配套数据分别管理。更新 MajsoulMax 时对比 `plugins/majsoulmax/PROVENANCE.md` 记录的基线，将变动移植进模块并保留本项目的独立路径、请求关联与友人房修复；更新 MajsoulData 时应同时更新 `max_data.yaml`、`liqi.desc`、RPC 表及 `data_version.json`，校验哈希后测试。当前没有自动远程更新按钮。
