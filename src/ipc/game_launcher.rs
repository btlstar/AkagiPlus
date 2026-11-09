//! Shared GUI launcher. Never restart a healthy capture just to open a game.
use crate::{
    config::{AppConfig, CaptureMode, Platform},
    ipc::{capture_supervisor, AppState},
    schema::CaptureStatus,
};
use anyhow::{bail, Context, Result};
use base64::{engine::general_purpose::STANDARD, Engine};
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::{
    path::{Path, PathBuf},
    time::Duration,
};
use tauri::State;
use tokio::{net::TcpStream, process::Command, sync::Mutex};

// A launch, a platform change and a patch operation must never overlap.
pub static OPERATION: Mutex<()> = Mutex::const_new(());
#[derive(Serialize)]
pub struct LaunchStatus {
    pub running: bool,
    pub client_path: String,
}

pub(crate) fn resource_root() -> PathBuf {
    let exe = std::env::current_exe().expect("executable path");
    let root = exe.parent().expect("executable directory");
    if cfg!(debug_assertions) && !root.join("plugins").exists() {
        PathBuf::from(env!("CARGO_MANIFEST_DIR"))
    } else {
        root.to_owned()
    }
}
pub fn python() -> Result<PathBuf> {
    let root = resource_root();
    for candidate in [
        root.join("runtime/python/x86_64-pc-windows-msvc/python.exe"),
        root.join(".venv/Scripts/python.exe"),
    ] {
        if candidate.is_file() {
            return Ok(candidate);
        }
    }
    bail!("运行依赖缺失，请重新解压完整 AkagiPlus 发布包。")
}
fn is_native(c: &AppConfig) -> bool {
    matches!(
        c.platform.kind,
        Platform::RiichiCity | Platform::Zhangxin | Platform::Amatsuki
    )
}
fn native_client(c: &AppConfig) -> PathBuf {
    if c.platform.kind == Platform::Amatsuki {
        return crate::capture::amatsuki::client_path(&c.proxy.amatsuki.client_path);
    }
    if c.platform.kind == Platform::Zhangxin {
        return crate::capture::zhangxin::client_path(&c.proxy.zhangxinplus.client_path);
    }
    let configured = &c.proxy.riichicity_unlock.client_path;
    if !configured.as_os_str().is_empty() {
        return configured.clone();
    }
    PathBuf::from(std::env::var_os("APPDATA").unwrap_or_default())
        .join("RiichicityLauncher/Game/Mahjong-JP.exe")
}
fn browser_profile(c: &AppConfig) -> Result<PathBuf> {
    if c.capture.mode == CaptureMode::Chromium {
        return crate::capture::chromium::profile::resolve_profile_dir(
            &c.capture.chromium.user_data_dir,
        );
    }
    Ok(resource_root().join(".local/browser"))
}
#[cfg(windows)]
fn process_ids(c: &AppConfig) -> Result<Vec<u32>> {
    use sysinfo::{ProcessRefreshKind, ProcessesToUpdate, System, UpdateKind};
    let profile = browser_profile(c)?
        .to_string_lossy()
        .to_lowercase()
        .replace('/', "\\");
    let client = native_client(c);
    let mut sys = System::new();
    sys.refresh_processes_specifics(
        ProcessesToUpdate::All,
        true,
        ProcessRefreshKind::nothing()
            .with_exe(UpdateKind::Always)
            .with_cmd(UpdateKind::Always),
    );
    let mut ids = Vec::new();
    for (pid, p) in sys.processes() {
        let matches = if is_native(c) {
            p.exe().is_some_and(|v| {
                v.to_string_lossy()
                    .eq_ignore_ascii_case(&client.to_string_lossy())
            })
        } else {
            p.cmd().iter().any(|a| {
                a.to_string_lossy().to_lowercase().replace('/', "\\")
                    == format!("--user-data-dir={profile}")
            })
        };
        if matches {
            ids.push(pid.as_u32());
        }
    }
    // Browser windows can belong to children of the profile-owning process.
    for _ in 0..3 {
        let children: Vec<_> = sys
            .processes()
            .iter()
            .filter(|(_, p)| p.parent().is_some_and(|p| ids.contains(&p.as_u32())))
            .map(|(pid, _)| pid.as_u32())
            .collect();
        for id in children {
            if !ids.contains(&id) {
                ids.push(id);
            }
        }
    }
    Ok(ids)
}
#[cfg(not(windows))]
fn process_ids(_: &AppConfig) -> Result<Vec<u32>> {
    Ok(Vec::new())
}
#[cfg(windows)]
fn focus(ids: &[u32]) -> bool {
    use windows_sys::core::BOOL;
    use windows_sys::Win32::{
        Foundation::{HWND, LPARAM},
        UI::WindowsAndMessaging::*,
    };
    struct Search<'a> {
        ids: &'a [u32],
        found: bool,
    }
    unsafe extern "system" fn visit(hwnd: HWND, data: LPARAM) -> BOOL {
        let s = &mut *(data as *mut Search<'_>);
        let mut pid = 0;
        GetWindowThreadProcessId(hwnd, &mut pid);
        if s.ids.contains(&pid) && IsWindowVisible(hwnd) != 0 && GetWindowTextLengthW(hwnd) > 0 {
            ShowWindow(hwnd, SW_RESTORE);
            s.found = SetForegroundWindow(hwnd) != 0;
            return 0;
        }
        1
    }
    let mut s = Search { ids, found: false };
    unsafe {
        EnumWindows(Some(visit), &mut s as *mut _ as LPARAM);
    };
    s.found
}
#[cfg(not(windows))]
fn focus(_: &[u32]) -> bool {
    false
}
async fn ids(c: AppConfig) -> Result<Vec<u32>> {
    tokio::task::spawn_blocking(move || process_ids(&c)).await?
}

#[tauri::command]
pub async fn get_game_launch_status(state: State<'_, AppState>) -> Result<LaunchStatus, String> {
    let c = state.config.read().await.clone();
    let running = !ids(c.clone()).await.map_err(|e| e.to_string())?.is_empty();
    Ok(LaunchStatus {
        running,
        client_path: if is_native(&c) {
            native_client(&c).to_string_lossy().into_owned()
        } else {
            String::new()
        },
    })
}
async fn ready(state: &AppState, c: &AppConfig) -> Result<()> {
    if matches!(c.platform.kind, Platform::Zhangxin | Platform::Amatsuki) {
        if !matches!(
            state.capture_control.lock().await.status,
            CaptureStatus::Running { .. }
        ) {
            capture_supervisor::spawn_capture_supervisor(state.clone()).await?;
        }
        return Ok(());
    }
    let running = matches!(
        state.capture_control.lock().await.status,
        CaptureStatus::Running { .. }
    );
    if !running {
        capture_supervisor::spawn_capture_supervisor(state.clone()).await?;
    }
    if c.capture.mode == CaptureMode::Chromium {
        return Ok(());
    }
    let mut addr: std::net::SocketAddr = c
        .proxy
        .addr
        .parse()
        .context("捕获地址格式有误，请在设置中检查。")?;
    if addr.ip().is_unspecified() {
        addr.set_ip(std::net::IpAddr::V4(std::net::Ipv4Addr::LOCALHOST));
    }
    if !addr.ip().is_loopback() {
        bail!("游戏启动入口需要本机捕获地址，请在设置中使用 127.0.0.1。")
    }
    tokio::time::timeout(Duration::from_secs(25), async {
        loop {
            if let CaptureStatus::Error { error, .. } = &state.capture_control.lock().await.status {
                bail!("捕获启动失败：{error}");
            }
            if TcpStream::connect(addr).await.is_ok()
                && (c.platform.kind != Platform::RiichiCity
                    || !c.proxy.riichicity_unlock.enabled
                    || crate::proxy::riichicity_unlock::status().phase == "ready")
            {
                return Ok(());
            }
            tokio::time::sleep(Duration::from_millis(250)).await;
        }
    })
    .await
    .context("捕获尚未就绪，请检查端口与装扮插件状态后重试。")??;
    Ok(())
}
fn browser_args(c: &AppConfig, profile: &Path, ca: &[u8]) -> Result<Vec<String>> {
    use hudsucker::rustls::pki_types::{pem::PemObject, CertificateDer};
    let certificate =
        CertificateDer::from_pem_slice(ca).context("本机捕获证书尚未生成，请稍后重试。")?;
    let (_, parsed) = x509_parser::parse_x509_certificate(certificate.as_ref())
        .map_err(|_| anyhow::anyhow!("本机捕获证书格式错误。"))?;
    let pin = STANDARD.encode(Sha256::digest(parsed.public_key().raw));
    let url = if c.capture.chromium.start_url.trim().is_empty() {
        if c.platform.kind == Platform::Tenhou {
            "https://tenhou.net/4/"
        } else {
            "https://game.maj-soul.com/1/"
        }
    } else {
        &c.capture.chromium.start_url
    };
    let u = reqwest::Url::parse(url).context("游戏地址格式错误")?;
    if !matches!(u.scheme(), "http" | "https") {
        bail!("游戏地址必须使用 HTTP 或 HTTPS。")
    }
    Ok(vec![
        format!("--user-data-dir={}", profile.display()),
        format!("--proxy-server=http://{}", c.proxy.addr),
        format!("--ignore-certificate-errors-spki-list={pin}"),
        "--no-first-run".into(),
        "--disable-quic".into(),
        "--test-type".into(),
        u.to_string(),
    ])
}
async fn launch_inner(state: &AppState) -> Result<LaunchStatus> {
    #[cfg(not(windows))]
    bail!("本次 GUI 游戏启动入口暂仅提供 Windows 版本。");
    let c = state.config.read().await.clone();
    let active = ids(c.clone()).await?;
    if !active.is_empty() {
        ready(state, &c).await?;
        tokio::task::spawn_blocking(move || focus(&active)).await?;
        return Ok(LaunchStatus {
            running: true,
            client_path: String::new(),
        });
    }
    if c.platform.kind == Platform::Amatsuki && !native_client(&c).is_file() {
        bail!("未找到天月客户端，请选择 mahjongP.exe。");
    }
    if c.platform.kind == Platform::Zhangxin && !native_client(&c).is_file() {
        bail!("未找到掌心客户端，请选择 zhangxinmj.exe。");
    }
    if c.platform.kind == Platform::RiichiCity && !native_client(&c).is_file() {
        bail!("未找到一番街客户端，请选择 Game 文件夹中的 Mahjong-JP.exe。");
    }
    if !matches!(c.platform.kind, Platform::Zhangxin | Platform::Amatsuki)
        && c.capture.mode == CaptureMode::Mitm
        && !c.proxy.enabled
    {
        bail!("请先在设置中启用 MITM 捕获。");
    }
    ready(state, &c).await?;
    if matches!(c.platform.kind, Platform::Zhangxin | Platform::Amatsuki)
        || c.capture.mode != CaptureMode::Chromium
    {
        let mut command = if is_native(&c) {
            let path = native_client(&c);
            let mut cmd = Command::new(&path);
            cmd.current_dir(path.parent().context("游戏路径无效")?);
            cmd
        } else {
            let executable = if c.capture.chromium.executable.is_empty() {
                crate::capture::chromium::detect::detect_system_browsers()
                    .into_iter()
                    .next()
                    .map(|b| b.path)
                    .context("未找到浏览器，请在设置中指定 Chrome 或 Edge。")?
            } else {
                PathBuf::from(&c.capture.chromium.executable)
            };
            let profile = browser_profile(&c)?;
            std::fs::create_dir_all(&profile)?;
            let ca = std::fs::read(crate::util::resolve_dir(&c.proxy.ca_dir).join("akagi-ca.cer"))
                .context("本机捕获证书尚未生成，请稍后重试。")?;
            let mut cmd = Command::new(executable);
            cmd.args(browser_args(&c, &profile, &ca)?);
            cmd
        };
        command
            .stdin(std::process::Stdio::null())
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null());
        // Do not hide the game/browser itself and do not terminate it when this IPC returns.
        command
            .spawn()
            .context("启动游戏失败，请检查游戏或浏览器路径。")?;
    }
    // Chromium is already being opened by its capture backend. Do not spawn another browser.
    for _ in 0..100 {
        let active = ids(c.clone()).await?;
        if !active.is_empty() {
            tokio::task::spawn_blocking(move || focus(&active)).await?;
            return Ok(LaunchStatus {
                running: true,
                client_path: String::new(),
            });
        }
        if let CaptureStatus::Error { error, .. } = &state.capture_control.lock().await.status {
            bail!("启动失败：{error}");
        }
        tokio::time::sleep(Duration::from_millis(200)).await;
    }
    bail!("未检测到游戏窗口，请检查客户端是否已退出，然后重试。")
}
#[tauri::command]
pub async fn launch_game(state: State<'_, AppState>) -> Result<LaunchStatus, String> {
    let _guard = OPERATION
        .try_lock()
        .map_err(|_| "正在启动或管理装扮，请稍候。".to_owned())?;
    launch_inner(&state).await.map_err(|e| format!("{e:#}"))
}
#[tauri::command]
pub async fn riichicity_local(
    action: String,
    state: State<'_, AppState>,
) -> Result<String, String> {
    let _guard = OPERATION
        .try_lock()
        .map_err(|_| "正在执行其他游戏操作，请稍候。".to_owned())?;
    if !["status", "install", "restore"].contains(&action.as_str()) {
        return Err("未知补丁操作".into());
    }
    let c = state.config.read().await.clone();
    let game = native_client(&c);
    let mut cmd = Command::new(python().map_err(|e| e.to_string())?);
    cmd.env("PYTHONUTF8", "1")
        .arg(resource_root().join("scripts/riichicity-local.py"))
        .arg(action)
        .arg("--game")
        .arg(game.parent().ok_or("游戏路径无效")?)
        .arg("--json")
        .arg("--state-dir")
        .arg(
            crate::util::user_config_root()
                .ok_or("无法定位用户配置目录")?
                .join("riichicity-local"),
        );
    #[cfg(windows)]
    cmd.creation_flags(0x08000000);
    let result = tokio::time::timeout(Duration::from_secs(120), cmd.kill_on_drop(true).output())
        .await
        .map_err(|_| "补丁操作超时，请检查客户端后重试。")?
        .map_err(|e| e.to_string())?;
    if !result.status.success() {
        return Err(String::from_utf8_lossy(&result.stderr).trim().to_owned());
    }
    Ok(String::from_utf8_lossy(&result.stdout).trim().to_owned())
}
#[tauri::command]
pub async fn zhangxinplus(action: String, state: State<'_, AppState>) -> Result<String, String> {
    let _guard = OPERATION
        .try_lock()
        .map_err(|_| "正在执行其他游戏操作，请稍候。".to_owned())?;
    if !["status", "install", "restore"].contains(&action.as_str()) {
        return Err("未知插件操作".into());
    }
    let c = state.config.read().await.clone();
    if c.platform.kind != Platform::Zhangxin {
        return Err("请先选择掌心麻将平台。".into());
    }
    let game = native_client(&c);
    if !game.is_file() {
        return Err("未找到掌心客户端，请先在游戏启动入口配置路径。".into());
    }
    let mut cmd = Command::new(python().map_err(|e| e.to_string())?);
    cmd.env("PYTHONUTF8", "1")
        .arg(resource_root().join("plugins/zhangxinplus/manage.py"))
        .arg(action)
        .arg(game.parent().ok_or("游戏路径无效")?)
        .arg("--json")
        .arg("--state-dir")
        .arg(
            crate::util::user_config_root()
                .ok_or("无法定位用户配置目录")?
                .join("zhangxinplus"),
        );
    #[cfg(windows)]
    cmd.creation_flags(0x08000000);
    let result = tokio::time::timeout(Duration::from_secs(120), cmd.kill_on_drop(true).output())
        .await
        .map_err(|_| "插件操作超时，请检查客户端。")?
        .map_err(|e| e.to_string())?;
    if !result.status.success() {
        return Err(String::from_utf8_lossy(&result.stderr).trim().to_owned());
    }
    Ok(String::from_utf8_lossy(&result.stdout).trim().to_owned())
}
#[cfg(test)]
mod tests {
    use super::*;
    use hudsucker::rcgen;
    #[test]
    fn browser_launch_pins_ca_and_has_only_game_url() {
        // Use the actual proxy CA constructor rather than a fake certificate parser.
        let key = rcgen::KeyPair::generate().unwrap();
        let cert = rcgen::CertificateParams::new(vec!["localhost".into()])
            .unwrap()
            .self_signed(&key)
            .unwrap();
        let args = browser_args(
            &AppConfig::default(),
            Path::new("profile with spaces"),
            cert.pem().as_bytes(),
        )
        .unwrap();
        assert!(args
            .iter()
            .any(|s| s.starts_with("--ignore-certificate-errors-spki-list=")));
        assert_eq!(args.iter().filter(|s| s.starts_with("https://")).count(), 1);
        assert!(!args.iter().any(|s| s == "--ignore-certificate-errors"
            || s == "about:blank"
            || s == "--no-sandbox"));
    }
    #[test]
    fn invalid_game_scheme_is_rejected() {
        let key = rcgen::KeyPair::generate().unwrap();
        let cert = rcgen::CertificateParams::new(vec![])
            .unwrap()
            .self_signed(&key)
            .unwrap();
        let mut c = AppConfig::default();
        c.capture.chromium.start_url = "file:///private".into();
        assert!(browser_args(&c, Path::new("profile"), cert.pem().as_bytes()).is_err());
    }
}
