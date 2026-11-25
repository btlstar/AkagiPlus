//! Read-only Archer readiness for the idle overlay. Never runs inference.
use crate::ipc::state::AppState;
use crate::schema::BotStatus;
use serde::{Deserialize, Serialize};
use std::sync::OnceLock;
use std::time::{Duration, Instant};
use tauri::State;
use tokio::process::Command;
use tokio::sync::Mutex;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ReadinessModel {
    players: u8,
    name: String,
    available: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArcherReadiness {
    state: String,
    message: String,
    #[serde(default)]
    code: Option<String>,
    models: Vec<ReadinessModel>,
    elapsed_ms: u64,
}

impl ArcherReadiness {
    fn status(state: &str, message: &str) -> Self {
        Self {
            state: state.into(),
            message: message.into(),
            code: None,
            models: vec![],
            elapsed_ms: 0,
        }
    }
}

struct CachedCheck {
    key: String,
    checked: Instant,
    result: ArcherReadiness,
}

static CACHE: OnceLock<Mutex<Option<CachedCheck>>> = OnceLock::new();

#[tauri::command]
pub async fn get_archer_readiness(
    force: Option<bool>,
    state: State<'_, AppState>,
) -> Result<ArcherReadiness, String> {
    let config = state.config.read().await.clone();
    let modes: Vec<u8> = [4, 3]
        .into_iter()
        .filter(|n| config.bot.enabled && config.bot.active_for(*n) == "archer-api")
        .collect();
    if modes.is_empty() {
        return Ok(ArcherReadiness::status("disabled", ""));
    }
    // A stopped game may leave an unfinished hand snapshot after leaving a room.
    // The bot lifecycle is authoritative; consult the hand only on bot errors.
    let bot_status = state.bot_status.read().await.clone();
    let in_game = match bot_status {
        BotStatus::Ready { .. } | BotStatus::Loading { .. } => true,
        BotStatus::Error { .. } => state
            .game_tracker
            .lock()
            .await
            .snapshot()
            .is_some_and(|s| !s.is_done),
        BotStatus::Idle | BotStatus::Stopped { .. } => false,
    };
    if in_game {
        return Ok(ArcherReadiness::status("in_game", ""));
    }
    let Some(runtime) = state.runtime.as_ref() else {
        return Ok(ArcherReadiness::status("error", "无法启动 Archer 连接检查"));
    };
    let dir = crate::util::resolve_dir(std::path::Path::new(&config.bot.dir)).join("archer-api");
    let stamp = std::fs::metadata(dir.join("settings.toml"))
        .ok()
        .map(|m| (m.len(), m.modified().ok()));
    let key = format!("{dir:?}|{:?}|{modes:?}|{stamp:?}", runtime.python());
    // Coalesce requests from remounts and cache free checks for 30 seconds.
    let mut cache = CACHE.get_or_init(|| Mutex::new(None)).lock().await;
    if !force.unwrap_or(false) {
        if let Some(previous) = cache.as_ref() {
            if previous.key == key && previous.checked.elapsed() < Duration::from_secs(30) {
                return Ok(previous.result.clone());
            }
        }
    }
    let mut command = Command::new(runtime.python());
    command
        .current_dir(&dir)
        .args(["configure.py", "--readiness", "--modes"]);
    for mode in modes {
        command.arg(mode.to_string());
    }
    command
        .env_remove("PYTHONHOME")
        .env_remove("PYTHONPATH")
        .env_remove("AKAGI_BOT_CONFIG")
        .kill_on_drop(true);
    #[cfg(target_os = "windows")]
    command.creation_flags(0x08000000); // CREATE_NO_WINDOW
    let result = match tokio::time::timeout(Duration::from_secs(12), command.output()).await {
        Ok(Ok(output)) if output.status.success() && output.stdout.len() <= 32_768 => {
            serde_json::from_slice::<ArcherReadiness>(&output.stdout)
                .unwrap_or_else(|_| ArcherReadiness::status("error", "连接检查返回异常"))
        }
        Err(_) => ArcherReadiness {
            code: Some("timeout".into()),
            ..ArcherReadiness::status("error", "连接检查超时，请稍后重试")
        },
        _ => ArcherReadiness::status("error", "无法启动 Archer 连接检查，请检查插件文件"),
    };
    *cache = Some(CachedCheck {
        key,
        checked: Instant::now(),
        result: result.clone(),
    });
    Ok(result)
}
