# AP 的 MajsoulMax-rs 组件

基于 MajsoulMax-rs 0.7.0，资源与协议快照为 0.16.293-4.0.51。
保留 GPL-3.0 许可，源码与构建文件随组件提供。来源及原始文件校验值见 SOURCE.json。

## 使用

在 AP 的“装扮”页启用雀魂 Max，重新开始捕获并重新登录雀魂。
AP 仍先把原始对局消息交给 AI，再处理本机外观显示。
原有 worker.py 会自动启动本目录的原生组件；无须单独启动 Rust Max 的代理。

个人选择保存到 AP 数据目录下的 rust/settings.mod.json，默认为：
.local/majsoulmax/rust/settings.mod.json。
从独立版迁移时，关闭 AP，将原版 liqi_config/settings.mod.json 复制到上述位置。
建议先备份已有目标文件；之后两边各自保存，互不覆盖。
升级组件时保留 .local 目录，不能用公开默认配置覆盖个人文件。
角色、皮肤及收藏等修改会保存到该 JSON，重启后继续使用。

## 构建

需要 Rust 2024 工具链。执行 cargo build --release 后，
将 target/release/majsoulmax-worker.exe 放到本目录，与 liqi_config 并列。
公开 settings.json 关闭自动更新和独立 AI；运行时不需要 GitHub token。
AP 通过 AKAGIPLUS_MAJSOULMAX_DATA_DIR 指定私有数据目录。
此组件仅接受标准输入输出 JSONL，不启动额外监听端口。
