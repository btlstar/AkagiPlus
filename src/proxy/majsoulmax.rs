// SPDX-License-Identifier: Apache-2.0
//! Process-isolated cosmetic adapter. Original frames reach the AI bridge first.
//! Python owns MajsoulMax's GPL implementation and never sees API keys or bot config.
use anyhow::{anyhow, bail, Context, Result};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use serde::{Deserialize, Serialize};
use std::{path::PathBuf, process::Stdio, sync::Arc, time::Duration};
use tokio::{
    io::{AsyncBufReadExt, AsyncReadExt, AsyncWriteExt, BufReader},
    process::{Child, ChildStdin, ChildStdout, Command},
    sync::Mutex,
};

const MAX_LINE: u64 = 12 * 1024 * 1024;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(default)]
pub struct MajsoulMaxConfig {
    pub enabled: bool,
    pub python: PathBuf,
    pub worker: PathBuf,
    pub data_dir: PathBuf,
}

impl Default for MajsoulMaxConfig {
    fn default() -> Self {
        Self {
            enabled: false,
            python: if cfg!(windows) {
                ".venv/Scripts/python.exe"
            } else {
                ".venv/bin/python"
            }
            .into(),
            worker: "plugins/majsoulmax/worker.py".into(),
            data_dir: ".local/majsoulmax".into(),
        }
    }
}

struct Process {
    _child: Child,
    input: ChildStdin,
    output: BufReader<ChildStdout>,
}

impl Process {
    async fn receive(&mut self) -> Result<serde_json::Value> {
        let mut line = Vec::new();
        (&mut self.output)
            .take(MAX_LINE + 1)
            .read_until(b'\n', &mut line)
            .await?;
        if line.len() as u64 > MAX_LINE || line.last() != Some(&b'\n') {
            bail!("MajsoulMax worker closed or exceeded response limit");
        }
        Ok(serde_json::from_slice(&line)?)
    }

    async fn exchange(&mut self, request: serde_json::Value) -> Result<serde_json::Value> {
        let mut line = serde_json::to_vec(&request)?;
        if line.len() as u64 > MAX_LINE {
            bail!("MajsoulMax request too large");
        }
        line.push(b'\n');
        self.input.write_all(&line).await?;
        self.input.flush().await?;
        let result = self.receive().await?;
        if result.get("error").is_some() {
            bail!("MajsoulMax frame rejected");
        }
        Ok(result)
    }
}

#[derive(Debug, Clone, Serialize)]
pub struct Status {
    pub phase: String,
    pub modified: u64,
    pub snapshot: String,
}
static STATUS: std::sync::LazyLock<std::sync::RwLock<Status>> = std::sync::LazyLock::new(|| {
    std::sync::RwLock::new(Status {
        phase: "stopped".into(),
        modified: 0,
        snapshot: String::new(),
    })
});
pub fn status() -> Status {
    STATUS.read().expect("MajsoulMax status poisoned").clone()
}
pub fn set_phase(phase: &str) {
    STATUS.write().expect("MajsoulMax status poisoned").phase = phase.into();
}
pub struct Flow {
    pub sender: tokio::sync::mpsc::Sender<Vec<u8>>,
    pub receiver: std::sync::Mutex<Option<tokio::sync::mpsc::Receiver<Vec<u8>>>>,
}
impl Flow {
    pub fn new() -> Arc<Self> {
        let (sender, receiver) = tokio::sync::mpsc::channel(64);
        Arc::new(Self {
            sender,
            receiver: std::sync::Mutex::new(Some(receiver)),
        })
    }
}

pub struct Worker {
    process: Mutex<Option<Process>>,
}

#[derive(Debug, Deserialize)]
struct WireTransform {
    data: String,
    drop: bool,
    inject_client: Vec<String>,
}

pub struct Transform {
    pub data: Vec<u8>,
    pub drop: bool,
    pub inject_client: Vec<Vec<u8>>,
}

impl Worker {
    pub async fn start(config: &MajsoulMaxConfig) -> Result<Arc<Self>> {
        let worker = std::fs::canonicalize(crate::util::resolve_dir(&config.worker))
            .context("MajsoulMax worker path not found")?;
        let configured_python = crate::util::resolve_dir(&config.python);
        let configured_python = if configured_python.is_file() {
            configured_python
        } else if config.python == std::path::Path::new(".venv/Scripts/python.exe") {
            crate::ipc::game_launcher::python()?
        } else {
            configured_python
        };
        let python = std::fs::canonicalize(&configured_python)
            .context("MajsoulMax Python environment not found")?;
        std::fs::create_dir_all(&config.data_dir)?;
        let data_dir = std::fs::canonicalize(&config.data_dir)?;
        let mut command = Command::new(python);
        command
            .arg("-u")
            .arg(worker)
            .env("AKAGIPLUS_MAJSOULMAX_DATA_DIR", data_dir)
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::inherit())
            .kill_on_drop(true);
        #[cfg(windows)]
        command.creation_flags(0x08000000); // CREATE_NO_WINDOW
        let mut child = command.spawn().context("cannot start MajsoulMax worker")?;
        let input = child.stdin.take().context("MajsoulMax stdin missing")?;
        let output = BufReader::new(child.stdout.take().context("MajsoulMax stdout missing")?);
        let mut process = Process {
            _child: child,
            input,
            output,
        };
        let ready = tokio::time::timeout(Duration::from_secs(8), process.receive()).await??;
        if ready["ready"] != true || ready["protocol"] != 1 {
            bail!("MajsoulMax worker did not become ready");
        }
        *STATUS.write().expect("MajsoulMax status poisoned") = Status {
            phase: "ready".into(),
            modified: 0,
            snapshot: ready["snapshot"].as_str().unwrap_or("").into(),
        };
        Ok(Arc::new(Self {
            process: Mutex::new(Some(process)),
        }))
    }

    async fn request(&self, request: serde_json::Value) -> Result<serde_json::Value> {
        // Include lock acquisition in the deadline; a dead worker cannot stall other flows.
        let result = tokio::time::timeout(Duration::from_millis(500), async {
            let mut guard = self.process.lock().await;
            let process = guard
                .as_mut()
                .ok_or_else(|| anyhow!("MajsoulMax disabled for this capture"))?;
            process.exchange(request).await
        })
        .await;
        match result {
            Ok(Ok(value)) => Ok(value),
            error => {
                // Kill and never reuse a desynchronised JSONL stream after cancellation.
                self.process.lock().await.take();
                set_phase("failed");
                match error {
                    Ok(Err(e)) => Err(e),
                    Err(_) => Err(anyhow!("MajsoulMax timed out; disabled for this capture")),
                    _ => unreachable!(),
                }
            }
        }
    }

    pub async fn transform(&self, flow: &str, from_client: bool, data: &[u8]) -> Result<Transform> {
        let value = self.request(serde_json::json!({
            "op": "frame", "flow": flow, "from_client": from_client, "data": STANDARD.encode(data),
        })).await?;
        let wire: WireTransform = serde_json::from_value(value)?;
        if wire.drop || !wire.inject_client.is_empty() || wire.data != STANDARD.encode(data) {
            STATUS.write().expect("MajsoulMax status poisoned").modified += 1;
        }
        Ok(Transform {
            data: STANDARD.decode(wire.data)?,
            drop: wire.drop,
            inject_client: wire
                .inject_client
                .into_iter()
                .map(|s| STANDARD.decode(s).map_err(Into::into))
                .collect::<Result<_>>()?,
        })
    }

    pub async fn close(&self, flow: &str) {
        let _ = self
            .request(serde_json::json!({"op": "close", "flow": flow}))
            .await;
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn private_paths_and_opt_in_default() {
        let cfg = MajsoulMaxConfig::default();
        assert!(!cfg.enabled);
        assert_eq!(cfg.data_dir, PathBuf::from(".local/majsoulmax"));
    }
}
