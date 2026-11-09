use super::*;
use futures_util::{SinkExt, StreamExt};
use hudsucker::{
    hyper_util::{client::legacy::Client, rt::TokioExecutor},
    Body, Proxy,
};
use std::time::Duration;
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpListener,
};

#[derive(Clone)]
struct RestoreRiichiCityHost;
impl hudsucker::HttpHandler for RestoreRiichiCityHost {
    async fn handle_request(
        &mut self,
        _ctx: &hudsucker::HttpContext,
        mut request: http::Request<Body>,
    ) -> hudsucker::RequestOrResponse {
        crate::proxy::riichicity_host::restore(&mut request);
        request.into()
    }
}

async fn headers(tcp: &mut TcpStream) -> String {
    let mut data = Vec::new();
    while !data.ends_with(b"\r\n\r\n") {
        data.push(tcp.read_u8().await.unwrap());
        assert!(data.len() < 16384);
    }
    String::from_utf8(data).unwrap()
}
#[tokio::test]
async fn http_and_websocket_both_use_local_adapter() {
    // The .invalid destination cannot resolve: neither leg can bypass the adapter.
    let adapter = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = adapter.local_addr().unwrap();
    let server = tokio::spawn(async move {
        let (mut tcp, _) = adapter.accept().await.unwrap();
        assert!(headers(&mut tcp)
            .await
            .starts_with("CONNECT game.invalid:80 HTTP/1.1"));
        tcp.write_all(b"HTTP/1.1 200 OK\r\n\r\n").await.unwrap();
        assert!(headers(&mut tcp).await.starts_with("GET /fixture HTTP/1.1"));
        tcp.write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\nConnection: close\r\n\r\nok")
            .await
            .unwrap();
        let (mut tcp, _) = adapter.accept().await.unwrap();
        assert!(headers(&mut tcp)
            .await
            .starts_with("CONNECT aga-alb.mahjong-jp.net:80 HTTP/1.1"));
        tcp.write_all(b"HTTP/1.1 200 OK\r\n\r\n").await.unwrap();
        let mut ws = hudsucker::tokio_tungstenite::accept_async(tcp)
            .await
            .unwrap();
        assert_eq!(
            ws.next().await.unwrap().unwrap().into_text().unwrap(),
            "before-cosmetics"
        );
        ws.send(hudsucker::tokio_tungstenite::tungstenite::Message::text(
            "after-cosmetics",
        ))
        .await
        .unwrap();
    });
    let store = Arc::new(CertStore::default());
    let client = Client::builder(TokioExecutor::new()).build::<_, Body>(http_connector(
        store.clone(),
        Some(address),
        None,
    ));
    let response = client
        .request(
            http::Request::get("http://game.invalid/fixture")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), 200);
    let temp = tempfile::tempdir().unwrap();
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let proxy_address = listener.local_addr().unwrap();
    let (stop, stopped) = tokio::sync::oneshot::channel::<()>();
    let proxy = Proxy::builder()
        .with_listener(listener)
        .with_ca(crate::proxy::ca::load_or_generate(temp.path()).unwrap())
        .with_http_connector(http_connector(store.clone(), Some(address), None))
        .with_websocket_connector(websocket_connector(store, None))
        .with_websocket_proxy(Some(address))
        .with_http_handler(RestoreRiichiCityHost)
        .with_graceful_shutdown(async {
            let _ = stopped.await;
        })
        .build()
        .unwrap();
    let task = tokio::spawn(proxy.start());
    let mut tcp = TcpStream::connect(proxy_address).await.unwrap();
    tcp.write_all(b"CONNECT 198.18.0.148:80 HTTP/1.1\r\nHost: 198.18.0.148:80\r\n\r\n")
        .await
        .unwrap();
    assert!(headers(&mut tcp).await.starts_with("HTTP/1.1 200"));
    use hudsucker::tokio_tungstenite::tungstenite::client::IntoClientRequest;
    let mut request = "ws://198.18.0.148:80/ws".into_client_request().unwrap();
    request.headers_mut().insert(
        http::header::HOST,
        "aga-alb.mahjong-jp.net".parse().unwrap(),
    );
    let (mut ws, _) = hudsucker::tokio_tungstenite::client_async(request, tcp)
        .await
        .unwrap();
    ws.send(hudsucker::tokio_tungstenite::tungstenite::Message::text(
        "before-cosmetics",
    ))
    .await
    .unwrap();
    let reply = tokio::time::timeout(Duration::from_secs(5), ws.next())
        .await
        .unwrap()
        .unwrap()
        .unwrap();
    assert_eq!(reply.into_text().unwrap(), "after-cosmetics");
    drop(ws);
    server.await.unwrap();
    let _ = stop.send(());
    tokio::time::timeout(Duration::from_secs(5), task)
        .await
        .unwrap()
        .unwrap()
        .unwrap();
}
#[tokio::test]
async fn rejected_adapter_never_falls_back_to_direct() {
    let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let address = listener.local_addr().unwrap();
    let server = tokio::spawn(async move {
        let (mut tcp, _) = listener.accept().await.unwrap();
        let _ = headers(&mut tcp).await;
        tcp.write_all(b"HTTP/1.1 502 Unavailable\r\n\r\n")
            .await
            .unwrap();
    });
    assert!(
        hudsucker::upstream::connect(address, &"https://game.invalid/".parse().unwrap())
            .await
            .is_err()
    );
    server.await.unwrap();
    assert!(hudsucker::upstream::connect(
        "192.0.2.1:41110".parse().unwrap(),
        &"https://game.invalid/".parse().unwrap()
    )
    .await
    .is_err());
}
#[tokio::test]
#[ignore = "requires user's external RiichiCityUnlock; no account or login"]
async fn real_external_adapter_https() {
    use crate::proxy::riichicity_unlock::{address, Adapter, RiichiCityUnlockConfig};
    let config = RiichiCityUnlockConfig {
        enabled: true,
        executable: std::env::var_os("AKAGIPLUS_TEST_UNLOCK").unwrap().into(),
        ..Default::default()
    };
    let adapter = Adapter::start(&config).await.unwrap();
    let connector = http_connector(
        Arc::new(CertStore::default()),
        Some(address()),
        Some(adapter.certificate.clone()),
    );
    let client = Client::builder(TokioExecutor::new()).build::<_, Body>(connector);
    let response = tokio::time::timeout(
        Duration::from_secs(20),
        client.request(
            http::Request::get("https://game.maj-soul.com/1/")
                .body(Body::empty())
                .unwrap(),
        ),
    )
    .await
    .unwrap()
    .unwrap();
    assert_eq!(response.status(), 200);
    // A real WS upgrade and payload also pass through the external adapter.
    let origin = TcpListener::bind("127.0.0.1:0").await.unwrap();
    let origin_address = origin.local_addr().unwrap();
    let origin_task = tokio::spawn(async move {
        let (tcp, _) = origin.accept().await.unwrap();
        let mut ws = hudsucker::tokio_tungstenite::accept_async(tcp)
            .await
            .unwrap();
        let message = ws.next().await.unwrap().unwrap();
        ws.send(message).await.unwrap();
    });
    let uri: http::Uri = format!("ws://{origin_address}/fixture").parse().unwrap();
    let tcp = hudsucker::upstream::connect(address(), &uri).await.unwrap();
    let (mut ws, _) = hudsucker::tokio_tungstenite::client_async(uri.to_string(), tcp)
        .await
        .unwrap();
    ws.send(hudsucker::tokio_tungstenite::tungstenite::Message::text(
        "real-adapter-fixture",
    ))
    .await
    .unwrap();
    let reply = tokio::time::timeout(Duration::from_secs(5), ws.next())
        .await
        .unwrap()
        .unwrap()
        .unwrap();
    assert_eq!(reply.into_text().unwrap(), "real-adapter-fixture");
    drop(ws);
    origin_task.await.unwrap();
    drop(adapter);
    // PyInstaller helpers may have children. Capture shutdown must release the
    // plugin's listening socket, including when async child cleanup is delayed.
    tokio::time::timeout(Duration::from_secs(5), async {
        while TcpStream::connect(address()).await.is_ok() {
            tokio::time::sleep(Duration::from_millis(50)).await;
        }
    })
    .await
    .expect("capture shutdown must release the external adapter port");
}
