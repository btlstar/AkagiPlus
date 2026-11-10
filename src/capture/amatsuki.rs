//! Amatsuki's local read-only message worker. No proxy or game-file patch.
use super::{CaptureBackend, CaptureCtx, CaptureDescriptor, CaptureKind, ShutdownToken};
use crate::{
    bridge::amatsuki::AmatsukiBridge,
    schema::{MjaiEvent, Notification},
};
use anyhow::{bail, Context, Result};
use async_trait::async_trait;
use std::{
    path::{Path, PathBuf},
    process::Stdio,
};
use tokio::{
    io::{AsyncBufReadExt, BufReader},
    process::Command,
};

pub fn client_path(configured: &Path) -> PathBuf {
    if !configured.as_os_str().is_empty() {
        return configured.to_owned();
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
        .map(|root| root.join("Steam/steamapps/common/天月麻雀/mahjongP.exe"))
        .find(|p| p.is_file())
        .unwrap_or_default()
}
pub struct AmatsukiBackend {
    exe: PathBuf,
    cosmetics: bool,
}
impl AmatsukiBackend {
    pub fn new(configured: &Path, cosmetics: bool) -> Result<Self> {
        let exe = client_path(configured);
        if !exe.is_file() {
            bail!("请先设置天月客户端 mahjongP.exe 的路径。");
        }
        Ok(Self { exe, cosmetics })
    }
}
struct EndOnDrop(crate::event_bus::MjaiBus);
impl Drop for EndOnDrop {
    fn drop(&mut self) {
        let _ = self.0.send(MjaiEvent::terminated_game());
    }
}
#[async_trait]
impl CaptureBackend for AmatsukiBackend {
    fn descriptor(&self) -> CaptureDescriptor {
        CaptureDescriptor {
            kind: CaptureKind::Native,
            label: "天月麻雀 · 普通立直 AI 建议".into(),
        }
    }
    async fn run(self: Box<Self>, ctx: CaptureCtx, shutdown: ShutdownToken) -> Result<()> {
        let root = crate::ipc::game_launcher::resource_root();
        let mut cmd = Command::new(crate::ipc::game_launcher::python()?);
        cmd.arg(root.join("plugins/amatsuki/host.py"))
            .arg("--game")
            .arg(&self.exe)
            .env("PYTHONIOENCODING", "utf-8")
            .env("PYTHONDONTWRITEBYTECODE", "1")
            .stdin(Stdio::null())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .kill_on_drop(true);
        #[cfg(windows)]
        cmd.creation_flags(0x08000000);
        if self.cosmetics {
            cmd.arg("--cosmetics");
        }
        let mut child = cmd
            .spawn()
            .context("无法启动天月消息捕获，请检查完整运行依赖。")?;
        let stdout = child.stdout.take().context("天月捕获输出缺失")?;
        let stderr = child.stderr.take().context("天月捕获错误输出缺失")?;
        let errors = tokio::spawn(async move {
            let mut lines = BufReader::new(stderr).lines();
            while let Ok(Some(line)) = lines.next_line().await {
                tracing::warn!(target:"akagi::capture::amatsuki","{line}");
            }
        });
        let _end = EndOnDrop(ctx.mjai_bus.clone());
        let mut lines = BufReader::new(stdout).lines();
        let mut bridge = AmatsukiBridge::default();
        let log = ctx
            .session
            .flow_logger("amatsuki", "native.mjai.jsonl", "Amatsuki local AI")?;
        let stop = shutdown.wait();
        tokio::pin!(stop);
        let result: Result<()> = async {
            loop {
                let line = tokio::select! { _=&mut stop=>break, line=lines.next_line()=>line? };
                let Some(line) = line else {
                    bail!("天月消息捕获已退出，请重新启动捕获。");
                };
                anyhow::ensure!(line.len() <= 256 * 1024, "天月消息长度超限");
                let value: serde_json::Value =
                    serde_json::from_str(&line).context("天月消息格式无效")?;
                match value["kind"].as_str() {
                    Some("event") => {
                        for event in bridge.accept(&value)? {
                            log.writeln(&serde_json::to_string(&event)?);
                            let _ = ctx.mjai_bus.send(event);
                        }
                    }
                    Some("error") => {
                        bail!("{}", value["message"].as_str().unwrap_or("天月捕获失败"))
                    }
                    Some("status") => {
                        let message = value["message"].as_str().unwrap_or("等待天月对局");
                        tracing::info!(target:"akagi::capture::amatsuki","{message}");
                        let _ = ctx
                            .notify_bus
                            .send(Notification::info(message).id("amatsuki-sync"));
                    }
                    _ => bail!("未知的天月消息类型"),
                }
            }
            Ok(())
        }
        .await;
        let _ = child.kill().await;
        let _ = child.wait().await;
        let _ = errors.await;
        result
    }
}
