mod ca;
pub mod certstore;
mod handler;
pub mod majsoulmax;
#[cfg(windows)]
mod owned_process;
pub mod rewrite;
mod riichicity_host;
pub mod riichicity_unlock;
mod upstream;

pub use handler::ProxyHandler;

use crate::{
    config::{HttpCaptureConfig, Platform, ProxyConfig},
    event_bus::{MjaiBus, NotifyBus},
    logger::Session,
    util::resolve_dir,
};
use anyhow::{Context, Result};
use hudsucker::Proxy;
use std::{future::Future, net::SocketAddr, str::FromStr, sync::Arc};
use tokio::sync::Notify;
use tracing::info;

/// Build and run the MITM proxy until `shutdown` resolves.
///
/// The argument list is long because this is the composition root for the
/// proxy: every collaborator it needs is injected rather than reached for,
/// which is what lets the integration tests drive it over a real socket
/// with buses and autoplay left out.
#[allow(clippy::too_many_arguments)]
pub async fn start_proxy<F>(
    config: ProxyConfig,
    http_cfg: HttpCaptureConfig,
    platform: Platform,
    session: Arc<Session>,
    mjai_tx: Option<MjaiBus>,
    notify_tx: Option<NotifyBus>,
    force_close: Arc<Notify>,
    inject: Option<crate::autoplay::inject::SharedInjectBus>,
    shutdown: F,
) -> Result<()>
where
    F: Future<Output = ()> + Send + 'static,
{
    let ca_dir = resolve_dir(&config.ca_dir);
    info!("Using CA dir: {}", ca_dir.display());

    let ca = ca::load_or_generate(&ca_dir)?;
    // Shared between the TLS verifier (which records what origins serve)
    // and the handler (which puts those values back into the client's
    // certificate report). See `certstore` and `rewrite::majsoul_cert`.
    let certs = Arc::new(certstore::CertStore::default());
    let addr = SocketAddr::from_str(&config.addr)
        .with_context(|| format!("Invalid proxy addr: {}", config.addr))?;

    // Keep ownership for the lifetime of this capture. Failure must not silently bypass cosmetics.
    let mut external = if config.riichicity_unlock.enabled && platform == Platform::RiichiCity {
        Some(riichicity_unlock::Adapter::start(&config.riichicity_unlock).await?)
    } else {
        riichicity_unlock::set_phase("disabled");
        None
    };
    let external_proxy = external.as_ref().map(|_| riichicity_unlock::address());
    let external_ca = external.as_ref().map(|adapter| adapter.certificate.clone());

    let majsoulmax = if config.majsoulmax.enabled && platform == Platform::Majsoul {
        majsoulmax::set_phase("starting");
        match majsoulmax::Worker::start(&config.majsoulmax).await {
            Ok(worker) => {
                info!("AkagiPlus MajsoulMax ready");
                if let Some(tx) = &notify_tx {
                    let _ = tx.send(
                        crate::schema::Notification::info("MajsoulMax 已就绪")
                            .body("装扮模块已加载；请重新登录游戏以加载装扮。"),
                    );
                }
                Some(worker)
            }
            Err(error) => {
                majsoulmax::set_phase("failed");
                tracing::warn!("MajsoulMax startup failed: {error:#}");
                if let Some(tx) = &notify_tx {
                    let _ = tx.send(
                        crate::schema::Notification::warn("MajsoulMax 未启动")
                            .body("请检查设置中的 Python 和插件路径；AI 捕获继续运行。")
                            .sticky()
                            .id("majsoulmax-error"),
                    );
                }
                None
            }
        }
    } else {
        majsoulmax::set_phase("disabled");
        None
    };
    let handler = ProxyHandler::new(
        session.clone(),
        platform,
        mjai_tx,
        notify_tx,
        force_close,
        http_cfg.policy(),
        certs.clone(),
        config.rewrite_certificate_report,
        config.block_telemetry,
        inject,
    )?
    .with_majsoulmax(majsoulmax);

    info!("Starting proxy on {addr}");

    let proxy = Proxy::builder()
        .with_addr(addr)
        .with_ca(ca)
        .with_http_connector(upstream::http_connector(
            certs.clone(),
            external_proxy,
            external_ca.clone(),
        ))
        .with_http_handler(handler.clone())
        .with_websocket_handler(handler)
        .with_websocket_connector(upstream::websocket_connector(certs.clone(), external_ca))
        .with_websocket_proxy(external_proxy)
        .with_graceful_shutdown(shutdown)
        .build()
        .context("Failed to build proxy")?;

    let result = if let Some(adapter) = external.as_mut() {
        tokio::select! {
            result = proxy.start() => result.context("Proxy stopped with error"),
            exit = adapter.wait() => {
                riichicity_unlock::set_phase("failed");
                Err(anyhow::anyhow!("RiichiCityUnlock 已停止（{exit:?}），游戏捕获已中止；请重启捕获"))
            }
        }
    } else {
        proxy.start().await.context("Proxy stopped with error")
    };
    majsoulmax::set_phase("stopped");
    result
}
