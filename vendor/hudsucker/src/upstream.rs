//! AkagiPlus addition. See AKAGIPLUS-PATCH.md.
use http::Uri;
use std::{io, net::SocketAddr, time::Duration};
use tokio::{
    io::{AsyncReadExt, AsyncWriteExt},
    net::TcpStream,
};

/// Open a tunnel without resolving the destination locally or consuming payload bytes.
/// Restricted to loopback adapters; no implicit direct fallback.
pub async fn connect(proxy: SocketAddr, destination: &Uri) -> io::Result<TcpStream> {
    if !proxy.ip().is_loopback() {
        return Err(io::Error::other("upstream must be loopback"));
    }
    let host = destination
        .host()
        .ok_or_else(|| io::Error::other("missing destination host"))?;
    let port = destination
        .port_u16()
        .unwrap_or(match destination.scheme_str() {
            Some("https" | "wss") => 443,
            _ => 80,
        });
    let host = host.trim_start_matches('[').trim_end_matches(']');
    let target = if host.contains(':') {
        format!("[{host}]:{port}")
    } else {
        format!("{host}:{port}")
    };
    tokio::time::timeout(Duration::from_secs(8), async {
        let mut tcp = TcpStream::connect(proxy).await?;
        tcp.write_all(format!("CONNECT {target} HTTP/1.1\r\nHost: {target}\r\n\r\n").as_bytes())
            .await?;
        let mut headers = Vec::new();
        loop {
            let byte = tcp.read_u8().await?;
            headers.push(byte);
            if headers.ends_with(b"\r\n\r\n") {
                break;
            }
            if headers.len() >= 16384 {
                return Err(io::Error::other("upstream headers too large"));
            }
        }
        let status = headers.split(|b| *b == b'\n').next().unwrap_or_default();
        if status.split(|b| *b == b' ').nth(1) != Some(b"200".as_slice()) {
            return Err(io::Error::other("local upstream rejected CONNECT"));
        }
        Ok(tcp)
    })
    .await
    .map_err(|_| io::Error::new(io::ErrorKind::TimedOut, "local upstream CONNECT timed out"))?
}
