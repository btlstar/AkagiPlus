# AkagiPlus

基於 [Akagi 3.8.0](https://github.com/shinkuan/Akagi) 的麻將 AI 與本機裝扮擴充，整合雀魂 MajsoulMax、一番街裝扮、掌心 ZhangxinPlus 與 GUI 遊戲啟動。

[简体中文](README.zh-CN.md) · [English](README.md) · [下載預發布版](https://github.com/btlstar/AkagiPlus/releases/tag/v3.8.0-plus.2)

![總覽與啟動入口](docs/images/overview.png)
![掌心裝扮管理](docs/images/cosmetics.png)
![對局頁](docs/images/game.png)
![掌心裝扮方案](docs/images/zhangxin-cosmetics.png)

AkagiPlus 截圖使用目前介面和示範設定；掌心畫面由使用者實測提供，未包含登入資料或密鑰。

## 下載與使用

下載 `AkagiPlus-3.8.0-plus.2-windows-x64.zip`，完整解壓後執行 `AkagiPlus.exe`，保留 `runtime`、`plugins` 等目錄。需要 Windows x64 與 WebView2，無須另外安裝 Python 或 Node。

在「總覽」選擇遊戲並啟動；在「裝扮」安裝、更新或還原插件，操作前請先退出遊戲。AI 密鑰和模型在「機器人」自行設定，新對局開始前連接，建議顯示於「對局」或懸浮窗。

- 雀魂：專用瀏覽器與 MajsoulMax，啟用裝扮時使用 MITM。
- 一番街：Windows 獨立客戶端，需自行配置並保持 Proxifier 運行；支援角色、皮膚、頭像、稱號、星標和方案。安全模式若包含自己，進桌時可能改用預設皮膚。
- 掌心：ZhangxinPlus 0.1.5，適配資源 **92217**，本機裝扮無須代理或憑證；友人局普通立直三麻、四麻 AI 已實測。特殊玩法、中途恢復與自動操作未支援，頭像與語音仍未完整適配。
- 天鳳：保留上游捕獲與 AI，本版未新增裝扮插件。

插件核驗已支援資源並備份原檔，未知更新會停止安裝。本機裝扮不改變伺服器擁有物、貨幣、獎勵或養成進度，不保證其他玩家視角可見。

天月麻將尚未接入：上游 v2 有歷史協定橋，v3 仍列為規劃中。裝扮與 AI 接入調查見[調查說明](docs/AMATSUKI_FEASIBILITY.md)。

## 更新與開發

發布包使用乾淨預設設定，不含私人密鑰、登入資料、憑證、日誌或遊戲資源。更新完整套件前退出程式並備份設定，保留使用者目錄中的原始資源恢復備份。

版本 `v3.8.0-plus.2` 跟隨已整合的上游基線，僅檢查本分支更新。預發布版本可於 Releases 手動下載。源碼開發保留 `start.bat`，日常遊戲入口在 GUI。

[開發說明](docs/AKAGIPLUS.md) · [發布指南](docs/RELEASE.md) · [ZhangxinPlus](plugins/zhangxinplus/README.md)。Akagi 與 ZhangxinPlus 採 Apache-2.0；MajsoulMax 改編部分保留 GPL-3.0 及對應源碼、許可和來源記錄，詳見 LICENSE.txt、NOTICE、LICENSES。外部 RiichiCityUnlock、Proxifier 及遊戲客戶端不隨包提供。
