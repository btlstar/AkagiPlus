//! Capture transports — supplies WebSocket frames or local game messages to the
//! [`crate::bridge::Bridge`] parser.
//!
//! - [`hudsucker_backend::HudsuckerBackend`] — MITM proxy; requires traffic
//!   routing and CA trust.
//! - [`chromium::ChromiumBackend`] — controlled Chromium browser, intercepts
//!   WebSocket frames via CDP. No proxy/CA setup.
//! - [`zhangxin::ZhangxinBackend`] — whitelisted local game-message queue.
//! - [`amatsuki::AmatsukiBackend`] — local Python / Frida capture worker.
//!
//! All implement [`CaptureBackend`] and emit mjai events through their platform
//! bridge. WebSocket transports use [`flow::FlowBridges`] for per-flow state.

pub mod amatsuki;
pub mod chromium;
pub mod flow;
pub mod http;
pub mod hudsucker_backend;
pub mod telemetry;
pub mod zhangxin;

use crate::autoplay::AutoplayContext;
use crate::config::Platform;
use crate::event_bus::{MjaiBus, NotifyBus};
use crate::logger::Session;
use anyhow::Result;
use async_trait::async_trait;
use std::future::Future;
use std::pin::Pin;
use std::sync::Arc;
use tokio::sync::watch;

/// Discriminant exposed in [`CaptureStatus`] / IPC payloads.
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CaptureKind {
    Mitm,
    Chromium,
    Native,
}

impl CaptureKind {
    pub fn as_str(self) -> &'static str {
        match self {
            CaptureKind::Mitm => "mitm",
            CaptureKind::Chromium => "chromium",
            CaptureKind::Native => "native",
        }
    }
}

/// Static per-backend descriptor. The supervisor surfaces this in
/// status messages so the UI can show "Running (Chromium @ /usr/bin/google-chrome)"
/// or similar.
#[derive(Debug, Clone)]
pub struct CaptureDescriptor {
    pub kind: CaptureKind,
    /// Human-readable description (listen addr for MITM, executable path
    /// for Chromium). Surface in UI; do not parse.
    pub label: String,
}

/// Durable shutdown signal: cancellation is remembered even during startup.
#[derive(Clone)]
pub struct ShutdownToken(watch::Receiver<bool>);
impl ShutdownToken {
    pub fn new() -> (Self, watch::Sender<bool>) {
        let (tx, rx) = watch::channel(false);
        (Self(rx), tx)
    }
    /// Resolves for existing and future waiters once shutdown is requested.
    pub fn wait(&self) -> Pin<Box<dyn Future<Output = ()> + Send + '_>> {
        Box::pin(async move {
            let mut rx = self.0.clone();
            let _ = rx.wait_for(|cancelled| *cancelled).await;
        })
    }
}
#[cfg(test)]
mod shutdown_tests {
    use super::*;
    use std::time::Duration;
    #[tokio::test]
    async fn shutdown_before_startup_is_remembered() {
        let (token, signal) = ShutdownToken::new();
        signal.send_replace(true);
        tokio::time::timeout(Duration::from_millis(100), token.wait())
            .await
            .unwrap();
        tokio::time::timeout(Duration::from_millis(100), token.clone().wait())
            .await
            .unwrap();
    }
    #[tokio::test]
    async fn shutdown_wakes_all_waiters_and_later_clones() {
        let (token, signal) = ShutdownToken::new();
        let other = token.clone();
        let a = tokio::spawn(async move { other.wait().await });
        let other = token.clone();
        let b = tokio::spawn(async move { other.wait().await });
        tokio::task::yield_now().await;
        signal.send_replace(true);
        tokio::time::timeout(Duration::from_millis(100), async {
            a.await.unwrap();
            b.await.unwrap();
            token.wait().await;
        })
        .await
        .unwrap();
    }
}

/// Everything a backend needs to push parsed mjai events into the rest of
/// the app. Cheap to clone (all `Arc`/`Sender`/`Notify`).
#[derive(Clone)]
pub struct CaptureCtx {
    pub session: Arc<Session>,
    pub platform: Platform,
    pub mjai_bus: MjaiBus,
    pub notify_bus: NotifyBus,
    /// Shared with the autoplay manager. The chromium backend writes the
    /// per-tab `Page` handle here when it observes a Majsoul WS;
    /// autoplay reads it to dispatch `Input.dispatchMouseEvent`. The
    /// MITM backend simply ignores this — it has no `Page`.
    pub autoplay: Option<Arc<AutoplayContext>>,
    /// What to record of the HTTP traffic this backend intercepts. Both
    /// backends honour it; `static_assets` is chromium-only.
    pub http: crate::config::HttpCaptureConfig,
}

/// A capture transport. Implementors run a long-lived I/O loop until
/// `shutdown` resolves or a fatal error occurs, pushing frames into the
/// bridge layer along the way.
#[async_trait]
pub trait CaptureBackend: Send {
    /// Run the backend. Must respect `shutdown` for graceful exit.
    /// Returns `Ok(())` on clean exit, `Err` otherwise.
    async fn run(self: Box<Self>, ctx: CaptureCtx, shutdown: ShutdownToken) -> Result<()>;

    /// Static description for status reporting. Called once at spawn time
    /// (and again after restart) — must not block.
    fn descriptor(&self) -> CaptureDescriptor;
}
