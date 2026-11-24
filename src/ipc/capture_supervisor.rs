//! Serialised capture lifecycle. A replacement starts only after its predecessor exits.

use crate::capture::{
    chromium::ChromiumBackend, hudsucker_backend::HudsuckerBackend, CaptureBackend, CaptureCtx,
    CaptureKind as RtCaptureKind, ShutdownToken,
};
use crate::config::CaptureMode;
use crate::event_bus::{CaptureStatusBus, NotifyBus};
use crate::ipc::state::{AppState, CaptureControl};
use crate::schema::{CaptureKind, CaptureStatus, Notification};
use anyhow::Result;
use std::time::Duration;
use std::{future::Future, sync::Arc};
use tokio::sync::{watch, Mutex};
use tracing::{error, info, warn};

fn schema_kind(k: RtCaptureKind) -> CaptureKind {
    match k {
        RtCaptureKind::Mitm => CaptureKind::Mitm,
        RtCaptureKind::Chromium => CaptureKind::Chromium,
        RtCaptureKind::Native => CaptureKind::Native,
    }
}

/// The lifecycle lock must be held until the old task has actually exited.
async fn stop_and_wait(
    control: &Arc<Mutex<CaptureControl>>,
    status_bus: &CaptureStatusBus,
    max_wait: Duration,
) -> bool {
    let (stop, task, force_close, generation) = {
        let mut ctl = control.lock().await;
        (
            ctl.stop.take(),
            ctl.task.take(),
            ctl.force_close.clone(),
            ctl.generation,
        )
    };
    let was_running = stop.is_some();
    force_close.notify_waiters();
    if let Some(tx) = stop {
        let _ = tx.send(());
    }
    if let Some(mut task) = task {
        if tokio::time::timeout(max_wait, &mut task).await.is_err() {
            warn!("capture supervisor: shutdown deadline reached; cancelling old task");
            task.abort();
            let _ = task.await;
        }
    }
    finish_run(control, status_bus, generation, CaptureStatus::Stopped).await;
    was_running
}

async fn finish_run(
    control: &Arc<Mutex<CaptureControl>>,
    status_bus: &CaptureStatusBus,
    generation: u64,
    next: CaptureStatus,
) {
    let mut ctl = control.lock().await;
    if ctl.generation != generation {
        return;
    }
    ctl.stop = None;
    ctl.status = next.clone();
    // Publish under the snapshot lock so a newer run cannot overtake this event.
    let _ = status_bus.send(next);
}

pub async fn stop_capture_inner(state: AppState) -> bool {
    let lifecycle = state.capture_control.lock().await.lifecycle.clone();
    let _guard = lifecycle.lock().await;
    stop_and_wait(
        &state.capture_control,
        &state.capture_status_bus,
        Duration::from_secs(2),
    )
    .await
}

pub async fn restart_capture(state: AppState) -> Result<()> {
    let lifecycle = state.capture_control.lock().await.lifecycle.clone();
    let _guard = lifecycle.lock().await;
    stop_and_wait(
        &state.capture_control,
        &state.capture_status_bus,
        Duration::from_secs(2),
    )
    .await;
    spawn_locked(state).await
}

pub async fn spawn_capture_supervisor(state: AppState) -> Result<()> {
    let lifecycle = state.capture_control.lock().await.lifecycle.clone();
    let _guard = lifecycle.lock().await;
    if state.capture_control.lock().await.stop.is_some() {
        return Ok(());
    }
    // Reap a naturally completed task before replacing it.
    stop_and_wait(
        &state.capture_control,
        &state.capture_status_bus,
        Duration::from_secs(2),
    )
    .await;
    spawn_locked(state).await
}

async fn spawn_locked(state: AppState) -> Result<()> {
    let result = start_backend(state.clone()).await;
    if let Err(error) = &result {
        let cfg = state.config.read().await;
        let kind = if matches!(
            cfg.platform.kind,
            crate::config::Platform::Amatsuki | crate::config::Platform::Zhangxin
        ) {
            CaptureKind::Native
        } else if cfg.capture.mode == CaptureMode::Chromium {
            CaptureKind::Chromium
        } else {
            CaptureKind::Mitm
        };
        let generation = state.capture_control.lock().await.generation;
        finish_run(
            &state.capture_control,
            &state.capture_status_bus,
            generation,
            CaptureStatus::Error {
                kind,
                descriptor: None,
                error: format!("{error:#}"),
            },
        )
        .await;
    }
    result
}

async fn start_backend(state: AppState) -> Result<()> {
    let (mode, proxy_cfg, chromium_cfg, http_cfg, platform) = {
        let cfg = state.config.read().await;
        (
            cfg.capture.mode,
            cfg.proxy.clone(),
            cfg.capture.chromium.clone(),
            cfg.capture.http.clone(),
            cfg.platform.kind,
        )
    };

    let (shutdown_token, shutdown_signal) = ShutdownToken::new();

    // Build backend per mode.
    let backend: Box<dyn CaptureBackend> = if platform == crate::config::Platform::Amatsuki {
        Box::new(crate::capture::amatsuki::AmatsukiBackend::new(
            &proxy_cfg.amatsuki.client_path,
            proxy_cfg.amatsuki.cosmetics_enabled,
        )?)
    } else if platform == crate::config::Platform::Zhangxin {
        Box::new(crate::capture::zhangxin::ZhangxinBackend::new(
            &proxy_cfg.zhangxinplus.client_path,
        )?)
    } else {
        match mode {
            CaptureMode::Mitm => {
                let force_close = {
                    let ctl = state.capture_control.lock().await;
                    ctl.force_close.clone()
                };
                Box::new(HudsuckerBackend::new(
                    proxy_cfg.clone(),
                    http_cfg.clone(),
                    force_close,
                ))
            }
            CaptureMode::Chromium => Box::new(ChromiumBackend::new(chromium_cfg)),
        }
    };
    let descriptor = backend.descriptor();
    let kind = schema_kind(descriptor.kind);

    // Status: emit Running with a descriptive label up front so the UI
    // sees an immediate transition from Stopped → Running. Backends that
    // fail mid-startup will flip back to Error from the spawned task.
    let label = match descriptor.kind {
        RtCaptureKind::Mitm => proxy_cfg.addr.clone(),
        RtCaptureKind::Chromium => format!("chromium ({})", descriptor.label),
        RtCaptureKind::Native => descriptor.label.clone(),
    };
    let ctx = CaptureCtx {
        session: state.log_session.clone(),
        platform,
        mjai_bus: state.mjai_bus.clone(),
        notify_bus: state.notify_bus.clone(),
        autoplay: Some(state.autoplay_context.clone()),
        http: http_cfg,
    };
    launch_run(
        state.capture_control.clone(),
        state.capture_status_bus.clone(),
        state.notify_bus.clone(),
        kind,
        label,
        shutdown_signal,
        async move { backend.run(ctx, shutdown_token).await },
    )
    .await;
    Ok(())
}

/// Owns the complete backend future; no detached shutdown relay can outlive it.
async fn launch_run(
    control: Arc<Mutex<CaptureControl>>,
    status_bus: CaptureStatusBus,
    notify_bus: NotifyBus,
    kind: CaptureKind,
    label: String,
    shutdown_signal: watch::Sender<bool>,
    run: impl Future<Output = Result<()>> + Send + 'static,
) {
    let (stop_tx, stop_rx) = tokio::sync::oneshot::channel::<()>();
    let mut ctl = control.lock().await;
    ctl.generation = ctl.generation.wrapping_add(1);
    let generation = ctl.generation;
    ctl.stop = Some(stop_tx);
    let running = CaptureStatus::Running {
        kind,
        descriptor: label.clone(),
    };
    ctl.status = running.clone();
    let _ = status_bus.send(running);
    info!(
        "capture supervisor: starting {} backend ({label})",
        kind_label(kind)
    );
    let task_control = control.clone();
    ctl.task = Some(tokio::spawn(async move {
        tokio::pin!(run);
        let result = tokio::select! {
            result = &mut run => result,
            _ = stop_rx => {
                shutdown_signal.send_replace(true);
                run.await
            }
        };
        let next = match result {
            Ok(()) => {
                info!("capture supervisor: stopped cleanly");
                CaptureStatus::Stopped
            }
            Err(e) => {
                let msg = format!("{e:#}");
                error!("capture supervisor: {msg}");
                let _ = notify_bus.send(
                    Notification::error(format!("{} capture stopped", kind_label(kind)))
                        .body(format!(
                            "{msg} — open Settings → Capture and click Restart."
                        ))
                        .sticky()
                        .id("capture-error"),
                );
                CaptureStatus::Error {
                    kind,
                    descriptor: Some(label),
                    error: msg,
                }
            }
        };
        finish_run(&task_control, &status_bus, generation, next).await;
    }));
}

fn kind_label(k: CaptureKind) -> &'static str {
    match k {
        CaptureKind::Mitm => "MITM",
        CaptureKind::Chromium => "Chromium",
        CaptureKind::Native => "本地消息",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicBool, Ordering};
    use tokio::sync::{broadcast, oneshot};

    fn fixtures() -> (Arc<Mutex<CaptureControl>>, CaptureStatusBus, NotifyBus) {
        (
            Arc::new(Mutex::new(CaptureControl::default())),
            broadcast::channel(32).0,
            broadcast::channel(16).0,
        )
    }
    struct MarkDropped(Arc<AtomicBool>);
    impl Drop for MarkDropped {
        fn drop(&mut self) {
            self.0.store(true, Ordering::SeqCst);
        }
    }

    #[tokio::test]
    async fn slow_old_worker_is_dropped_before_new_platform_starts() {
        let (control, status, notify) = fixtures();
        let dropped = Arc::new(AtomicBool::new(false));
        let (started, ready) = oneshot::channel();
        let (token, signal) = ShutdownToken::new();
        let drop_flag = dropped.clone();
        launch_run(
            control.clone(),
            status.clone(),
            notify.clone(),
            CaptureKind::Native,
            "Amatsuki".into(),
            signal,
            async move {
                let _guard = MarkDropped(drop_flag);
                let _ = started.send(());
                token.wait().await;
                std::future::pending::<Result<()>>().await
            },
        )
        .await;
        ready.await.unwrap();
        assert!(stop_and_wait(&control, &status, Duration::from_millis(20)).await);
        assert!(dropped.load(Ordering::SeqCst));
        let (token, signal) = ShutdownToken::new();
        launch_run(
            control.clone(),
            status.clone(),
            notify,
            CaptureKind::Native,
            "Zhangxin".into(),
            signal,
            async move {
                token.wait().await;
                Ok(())
            },
        )
        .await;
        tokio::task::yield_now().await;
        let ctl = control.lock().await;
        assert!(ctl.stop.is_some());
        assert!(
            matches!(&ctl.status, CaptureStatus::Running { descriptor, .. } if descriptor == "Zhangxin")
        );
        drop(ctl);
        stop_and_wait(&control, &status, Duration::from_millis(100)).await;
    }

    #[tokio::test]
    async fn stale_completion_cannot_clear_new_platform_control() {
        let (control, status, notify) = fixtures();
        let (token, signal) = ShutdownToken::new();
        launch_run(
            control.clone(),
            status.clone(),
            notify,
            CaptureKind::Native,
            "Zhangxin".into(),
            signal,
            async move {
                token.wait().await;
                Ok(())
            },
        )
        .await;
        let generation = control.lock().await.generation;
        finish_run(
            &control,
            &status,
            generation.wrapping_sub(1),
            CaptureStatus::Stopped,
        )
        .await;
        let ctl = control.lock().await;
        assert!(ctl.stop.is_some());
        assert!(matches!(ctl.status, CaptureStatus::Running { .. }));
        drop(ctl);
        stop_and_wait(&control, &status, Duration::from_millis(100)).await;
    }

    #[tokio::test]
    async fn immediate_stop_is_not_lost_during_worker_startup() {
        let (control, status, notify) = fixtures();
        let (token, signal) = ShutdownToken::new();
        launch_run(
            control.clone(),
            status.clone(),
            notify,
            CaptureKind::Native,
            "Amatsuki".into(),
            signal,
            async move {
                tokio::time::sleep(Duration::from_millis(20)).await;
                token.wait().await;
                Ok(())
            },
        )
        .await;
        assert!(stop_and_wait(&control, &status, Duration::from_secs(1)).await);
        let ctl = control.lock().await;
        assert!(ctl.task.is_none());
        assert!(ctl.stop.is_none());
        assert!(matches!(ctl.status, CaptureStatus::Stopped));
    }

    #[tokio::test]
    async fn lifecycle_lock_serialises_overlapping_switches() {
        let (control, status, notify) = fixtures();
        let lifecycle = control.lock().await.lifecycle.clone();
        let (token, signal) = ShutdownToken::new();
        launch_run(
            control.clone(),
            status.clone(),
            notify.clone(),
            CaptureKind::Native,
            "Amatsuki".into(),
            signal,
            async move {
                token.wait().await;
                Ok(())
            },
        )
        .await;
        let _first = lifecycle.lock().await;
        let c = control.clone();
        let s = status.clone();
        let n = notify.clone();
        let lock = lifecycle.clone();
        let next = tokio::spawn(async move {
            let _second = lock.lock().await;
            stop_and_wait(&c, &s, Duration::from_millis(100)).await;
            let (token, signal) = ShutdownToken::new();
            launch_run(
                c,
                s,
                n,
                CaptureKind::Native,
                "Zhangxin".into(),
                signal,
                async move {
                    token.wait().await;
                    Ok(())
                },
            )
            .await;
        });
        tokio::task::yield_now().await;
        assert!(!next.is_finished());
        drop(_first);
        next.await.unwrap();
        assert!(
            matches!(&control.lock().await.status, CaptureStatus::Running { descriptor, .. } if descriptor == "Zhangxin")
        );
        stop_and_wait(&control, &status, Duration::from_millis(100)).await;
    }
}
