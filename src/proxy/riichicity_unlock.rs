//! Optional external RiichiCityUnlock adapter; binaries stay outside this repository.
use anyhow::{bail, Context, Result};
use hudsucker::rustls::pki_types::{pem::PemObject, CertificateDer};
use serde::{Deserialize, Serialize};
use std::{net::SocketAddr, path::PathBuf, process::Stdio, sync::RwLock, time::Duration};
use tokio::{
    net::TcpStream,
    process::{Child, Command},
};

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(default)]
pub struct RiichiCityUnlockConfig {
    pub enabled: bool,
    pub executable: PathBuf,
    pub ca_path: PathBuf,
    pub client_path: PathBuf,
    pub injector_path: PathBuf,
}
#[derive(Clone, Serialize)]
pub struct Status {
    pub phase: String,
}
static PHASE: RwLock<String> = RwLock::new(String::new());
pub fn set_phase(value: &str) {
    *PHASE.write().expect("adapter status") = value.into();
}
pub fn status() -> Status {
    Status {
        phase: PHASE.read().expect("adapter status").clone(),
    }
}
pub fn address() -> SocketAddr {
    SocketAddr::from(([127, 0, 0, 1], 41110))
}

pub struct Adapter {
    _child: Child,
    #[cfg(windows)]
    _job: super::owned_process::Job,
    pub certificate: CertificateDer<'static>,
}
impl Drop for Adapter {
    fn drop(&mut self) {
        if status().phase != "failed" {
            set_phase("stopped");
        }
    }
}
impl Adapter {
    pub async fn wait(&mut self) -> std::io::Result<std::process::ExitStatus> {
        self._child.wait().await
    }
    pub async fn start(config: &RiichiCityUnlockConfig) -> Result<Self> {
        set_phase("starting");
        let result = Self::start_inner(config).await;
        set_phase(if result.is_ok() { "ready" } else { "failed" });
        result
    }
    async fn start_inner(config: &RiichiCityUnlockConfig) -> Result<Self> {
        if !config.executable.is_absolute() || !config.executable.is_file() {
            bail!("请在装扮页选择 RiichiCityUnlock.exe 的完整路径");
        }
        if TcpStream::connect(address()).await.is_ok() {
            bail!("127.0.0.1:41110 已被占用，请关闭单独运行的 RiichiCityUnlock 后重启捕获");
        }
        let log_dir = crate::util::resolve_dir(std::path::Path::new(".local/riichicity"));
        std::fs::create_dir_all(&log_dir)?;
        let log = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(log_dir.join("unlock.log"))?;
        let mut command = Command::new(&config.executable);
        command
            .current_dir(
                config
                    .executable
                    .parent()
                    .context("invalid adapter directory")?,
            )
            .stdin(Stdio::null())
            .stdout(log.try_clone()?)
            .stderr(log)
            .kill_on_drop(true);
        #[cfg(windows)]
        command.creation_flags(0x08000000);
        let mut child = command.spawn().context("RiichiCityUnlock 启动失败")?;
        #[cfg(windows)]
        let job = match super::owned_process::Job::attach(&child) {
            Ok(job) => job,
            Err(error) => {
                let _ = child.kill().await;
                return Err(error).context("无法管理 RiichiCityUnlock 子进程，已停止启动");
            }
        };
        let ready = tokio::time::timeout(Duration::from_secs(30), async {
            loop {
                if child.try_wait()?.is_some() {
                    bail!("RiichiCityUnlock 已退出，请查看本机 unlock.log");
                }
                if TcpStream::connect(address()).await.is_ok() {
                    return Ok::<_, anyhow::Error>(());
                }
                tokio::time::sleep(Duration::from_millis(200)).await;
            }
        })
        .await
        .context("RiichiCityUnlock 启动超时")?;
        ready?;
        let path = if config.ca_path.as_os_str().is_empty() {
            dirs::home_dir()
                .context("无法定位用户目录")?
                .join(".mitmproxy/mitmproxy-ca-cert.pem")
        } else {
            config.ca_path.clone()
        };
        let bytes = std::fs::read(&path)
            .context("无法读取 RiichiCityUnlock 公共 CA 证书，请在装扮页指定证书路径")?;
        let certificate = public_certificate(&bytes)?;
        Ok(Self {
            _child: child,
            #[cfg(windows)]
            _job: job,
            certificate,
        })
    }
}
fn public_certificate(bytes: &[u8]) -> Result<CertificateDer<'static>> {
    if bytes.len() > 1_048_576 || bytes.windows(11).any(|x| x == b"PRIVATE KEY") {
        bail!("请选择公共 CA 证书文件，不要选择包含私钥的 PEM 文件");
    }
    let cert =
        CertificateDer::from_pem_slice(bytes).context("无法解析 RiichiCityUnlock 公共 CA 证书")?;
    let (_, parsed) = x509_parser::parse_x509_certificate(cert.as_ref())
        .map_err(|_| anyhow::anyhow!("无效的 CA 证书"))?;
    if !parsed.is_ca() {
        bail!("所选证书不是 CA 证书");
    }
    let mut roots = hudsucker::rustls::RootCertStore::empty();
    roots.add(cert.clone()).context("无法载入插件 CA 证书")?;
    Ok(cert)
}
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn rejects_private_keys_and_garbage() {
        assert!(public_certificate(b"-----BEGIN PRIVATE KEY-----").is_err());
        assert!(public_certificate(b"not a certificate").is_err());
        assert!(!RiichiCityUnlockConfig::default().enabled);
    }
}
