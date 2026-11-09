# Windows 发布准备

版本：`v3.8.0-plus.2`。上游基线：Akagi v3.8.0，提交 `63cea4b5d23d83bbee8d56bc3b9d547cca2046c3`。

## 构建

1. 配好 Rust/MSVC、Node、protoc，以及源代码依赖，见 AKAGIPLUS.md。
2. 使用上游固定的 python-build-standalone 3.12.13 / 20260414 Windows x64 运行时和 uv 0.11.8，放在 runtime/python 与 runtime/uv 的 x86_64-pc-windows-msvc 子目录。
3. 在便携 Python 中通过 `python.exe -m pip install -r scripts/release-requirements.txt` 安装已锁定的完整依赖；运行时下载 URL 与 SHA-256 见 docs/runtime-lock.json。保留各依赖的许可文件，不复制开发虚拟环境。
4. 运行 scripts/build-release.ps1。构建使用 custom-protocol，前端嵌入 EXE；不依赖本机 Vite 服务。
5. 在干净解压目录验证 GUI 启动、配置保存、装扮状态和依赖。测试产生的配置与日志不得重新打进发布包。

打包脚本使用白名单，只含 EXE、干净默认配置、必要插件源码、便携运行时、许可、README 与文件摘要。不会复制 .local、证书、日志、浏览器资料、游戏补丁产物或外部 RiichiCityUnlock 程序。原生游戏恢复备份放在用户配置目录，不随包迁移或删除。

## 上传

在 GitHub Desktop 检查改动，填 docs/COMMIT_MESSAGE.md 中的 Summary 和 Description，再 Commit、Push。Commit 只创建本地记录，Push 才同步 GitHub。

在 GitHub 仓库 Releases 中创建新版本，Tag 填 v3.8.0-plus.2，目标选择已推送的发布提交。标题填 AkagiPlus 3.8.0 · Plus 2，正文复制 docs/RELEASE_NOTES.md，附上 dist 中的 ZIP 和 .zip.sha256。

本分支的首次发布建议勾选 Pre-release，完成用户复测后再转为正式版；tag 的 plus 后缀表示分支修订，本身不代替 GitHub 发布状态。构建脚本不自动提交或上传；发布操作仅按用户明确指令执行。

后续同基线修复递增 plus.3；合并上游 3.8.1 后改为 3.8.1-plus.1。更新检查仅访问 btlstar/AkagiPlus，下载完整包手动更新，不替换为上游 EXE。
