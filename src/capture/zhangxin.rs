//! Local decoded-message queue; no interception certificate or proxy required.
use super::{CaptureBackend, CaptureCtx, CaptureDescriptor, CaptureKind, ShutdownToken};
use crate::{bridge::zhangxin::ZhangxinBridge, schema::Notification};
use anyhow::{bail, Context, Result};
use async_trait::async_trait;
use serde_json::{json, Value};
use std::{
    path::{Path, PathBuf},
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tokio::io::{AsyncReadExt, AsyncSeekExt};

pub fn client_path(configured: &Path) -> PathBuf {
    if !configured.as_os_str().is_empty() {
        return configured.to_path_buf();
    }
    let mut roots: Vec<PathBuf> = std::env::var_os("ProgramFiles(x86)")
        .into_iter()
        .map(PathBuf::from)
        .collect();
    roots.extend([
        PathBuf::from(r"D:\Program Files (x86)"),
        PathBuf::from(r"C:\Program Files (x86)"),
    ]);
    roots
        .into_iter()
        .map(|p| p.join("zhangxinmajiang/zhangxinmj.exe"))
        .find(|p| p.is_file())
        .unwrap_or_default()
}
pub struct ZhangxinBackend {
    root: PathBuf,
}
impl ZhangxinBackend {
    pub fn new(configured: &Path) -> Result<Self> {
        let exe = client_path(configured);
        if !exe.is_file() {
            bail!("请先设置掌心麻将客户端路径。")
        }
        let root = exe
            .parent()
            .context("无效的掌心路径")?
            .join("zhangxinmj_Data/_Data/Mahjong");
        Ok(Self { root })
    }
}
struct Lease {
    path: PathBuf,
    session: String,
}
impl Drop for Lease {
    fn drop(&mut self) {
        if let Ok(raw) = std::fs::read(&self.path) {
            if serde_json::from_slice::<Value>(&raw)
                .ok()
                .is_some_and(|v| v["session"].as_str() == Some(&self.session))
            {
                let _ = std::fs::remove_file(&self.path);
            }
        }
    }
}
// Clear the live AI state even if queue I/O fails, not only on an explicit stop.
struct EndOnDrop(crate::event_bus::MjaiBus);
impl Drop for EndOnDrop {
    fn drop(&mut self) {
        let _ = self.0.send(crate::schema::MjaiEvent::terminated_game());
    }
}
fn epoch() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}
#[async_trait]
impl CaptureBackend for ZhangxinBackend {
    fn descriptor(&self) -> CaptureDescriptor {
        CaptureDescriptor {
            kind: CaptureKind::Native,
            label: "掌心全民麻将 · 普通立直 AI 建议".into(),
        }
    }
    async fn run(self: Box<Self>, ctx: CaptureCtx, shutdown: ShutdownToken) -> Result<()> {
        if tokio::fs::read_to_string(self.root.join("version_num.txt"))
            .await?
            .trim()
            != "92217"
        {
            bail!("掌心资源版本未适配，请更新 ZhangxinPlus。")
        }
        // Require the installed AI-capable patch, rather than claiming capture
        // is working while a previous cosmetics-only patch is installed.
        let journal = crate::util::user_config_root()
            .context("无法定位用户配置目录")?
            .join("zhangxinplus/install.json");
        let record: Value = serde_json::from_slice(
            &tokio::fs::read(journal)
                .await
                .context("请先在装扮页安装 / 更新 ZhangxinPlus。")?,
        )?;
        let payload = std::fs::read_to_string(
            crate::ipc::game_launcher::resource_root()
                .join("plugins/zhangxinplus/local_cosmetics.lua"),
        )?;
        use sha2::{Digest, Sha256};
        let hash: String = Sha256::digest(payload.replace("\r\n", "\n").as_bytes())
            .iter()
            .map(|b| format!("{b:02x}"))
            .collect();
        if record["phase"] != "installed"
            || record["payload_sha256"].as_str() != Some(hash.as_str())
        {
            bail!("请先退出掌心，在装扮页更新 ZhangxinPlus，再开始捕获。")
        }
        let installed_game = record["game"].as_str().context("插件安装记录缺失")?;
        if std::fs::canonicalize(installed_game)?
            != std::fs::canonicalize(
                self.root
                    .parent()
                    .unwrap()
                    .parent()
                    .unwrap()
                    .parent()
                    .unwrap(),
            )?
        {
            bail!("插件安装记录不属于当前掌心路径，请重新安装插件。")
        }
        let files = record["files"].as_array().context("插件安装记录不完整")?;
        for name in [
            "df6b54478d440170373e336b88ffe419",
            "6356fb4c08102b577abf1dead61d6444",
        ] {
            let relative = format!("_Data/Mahjong/{name}");
            let expected = files
                .iter()
                .find(|x| x["relative"].as_str() == Some(relative.as_str()))
                .and_then(|x| x["patched_sha256"].as_str())
                .context("插件文件记录缺失")?;
            let actual: String = Sha256::digest(tokio::fs::read(self.root.join(name)).await?)
                .iter()
                .map(|b| format!("{b:02x}"))
                .collect();
            if actual != expected {
                bail!("掌心更新覆盖了插件，请退出游戏并更新 ZhangxinPlus。")
            }
        }
        let session = SystemTime::now()
            .duration_since(UNIX_EPOCH)?
            .as_nanos()
            .to_string();
        let lease = Lease {
            path: self.root.join("zhangxinplus-ai-control.json"),
            session: session.clone(),
        };
        let output = self.root.join("zhangxinplus-ai.jsonl");
        tokio::fs::write(&output, b"").await?;
        let log = ctx.session.flow_logger(
            "zhangxin",
            &format!("local-{session}.mjai.jsonl"),
            "Zhangxin local AI",
        )?;
        let _end = EndOnDrop(ctx.mjai_bus.clone());
        let stop = shutdown.wait();
        tokio::pin!(stop);
        let mut bridge = ZhangxinBridge::new();
        let mut cursor = 0u64;
        let mut pending = Vec::new();
        let mut last_issue = None;
        let mut renew = 0;
        let mut tick = tokio::time::interval(Duration::from_millis(100));
        loop {
            tokio::select! { _=&mut stop=>break,_=tick.tick()=>{} }
            if epoch() >= renew {
                // Replace, rather than truncate, so the game never reads half a lease.
                let temp = self.root.join("zhangxinplus-ai-control.tmp");
                tokio::fs::write(
                    &temp,
                    serde_json::to_vec(
                        &json!({"enabled":true,"session":session,"expires":epoch()+15}),
                    )?,
                )
                .await?;
                tokio::fs::rename(temp, &lease.path).await?;
                renew = epoch() + 5;
            }
            let mut file = tokio::fs::File::open(&output).await?;
            let size = file.metadata().await?.len();
            if size < cursor {
                cursor = 0;
                pending.clear();
                for e in bridge.reset("消息队列已刷新，等待重新同步。") {
                    let _ = ctx.mjai_bus.send(e);
                }
            }
            if size.saturating_sub(cursor) > 8 * 1024 * 1024 {
                bail!("掌心消息积压过多，请重启捕获并重新进入房间。")
            }
            file.seek(std::io::SeekFrom::Start(cursor)).await?;
            let len = file.read_to_end(&mut pending).await?;
            cursor += len as u64;
            let end = pending
                .iter()
                .rposition(|b| *b == b'\n')
                .map(|i| i + 1)
                .unwrap_or(0);
            for line in pending[..end]
                .split(|b| *b == b'\n')
                .filter(|s| !s.is_empty())
            {
                let envelope: Value = match serde_json::from_slice(line) {
                    Ok(v) => v,
                    Err(_) => {
                        for e in bridge.reset("掌心消息损坏，等待重新入房。") {
                            let _ = ctx.mjai_bus.send(e);
                        }
                        continue;
                    }
                };
                if envelope["session"].as_str() != Some(session.as_str()) {
                    continue;
                }
                for event in bridge.accept(&envelope) {
                    if let Ok(raw) = serde_json::to_string(&event) {
                        log.writeln(&raw);
                    }
                    let _ = ctx.mjai_bus.send(event);
                }
            }
            pending.drain(..end);
            if pending.len() > 256 * 1024 {
                bail!("掌心消息长度超限。")
            }
            if bridge.issue != last_issue {
                if let Some(issue) = &bridge.issue {
                    tracing::info!(target: "akagi::capture::zhangxin", "{issue}");
                    let _ = ctx
                        .notify_bus
                        .send(Notification::info(issue).id("zhangxin-sync"));
                }
                if bridge.issue.is_none() {
                    tracing::info!(target: "akagi::capture::zhangxin", "掌心对局已同步，AI 事件已接通");
                }
                last_issue = bridge.issue.clone();
            }
        }
        drop(lease);
        Ok(())
    }
}
