//! Restore Riichi City's original Host when a redirector supplied a DNS fake IP.
//! This keeps domain-based external plugins and TLS upstream SNI consistent.
use http::{header::HOST, uri::Authority, Method, Request, Uri};
use std::net::Ipv4Addr;

pub fn restore<B>(request: &mut Request<B>) -> bool {
    if request.method() == Method::CONNECT {
        return false;
    }
    let Some(ip) = request
        .uri()
        .host()
        .and_then(|s| s.parse::<Ipv4Addr>().ok())
    else {
        return false;
    };
    let octets = ip.octets();
    if octets[0] != 198 || !matches!(octets[1], 18 | 19) {
        return false;
    }
    let Some(host) = request.headers().get(HOST).and_then(|v| v.to_str().ok()) else {
        return false;
    };
    if host.contains('@') {
        return false;
    }
    let Ok(authority) = host.parse::<Authority>() else {
        return false;
    };
    let domain = authority.host().to_ascii_lowercase();
    if domain != "mahjong-jp.net" && !domain.ends_with(".mahjong-jp.net") {
        return false;
    }
    let port = request
        .uri()
        .port_u16()
        .unwrap_or_else(|| match request.uri().scheme_str() {
            Some("https" | "wss") => 443,
            _ => 80,
        });
    // A conflicting explicit port is ambiguous; retain the original request.
    if authority
        .port_u16()
        .is_some_and(|header_port| header_port != port)
    {
        return false;
    }
    let Ok(authority) = format!("{domain}:{port}").parse::<Authority>() else {
        return false;
    };
    let mut parts = request.uri().clone().into_parts();
    parts.authority = Some(authority);
    let Ok(uri) = Uri::from_parts(parts) else {
        return false;
    };
    *request.uri_mut() = uri;
    true
}

#[cfg(test)]
mod tests {
    use super::*;
    fn request(uri: &str, host: &str) -> Request<()> {
        Request::builder()
            .uri(uri)
            .header(HOST, host)
            .body(())
            .unwrap()
    }
    #[test]
    fn restores_fake_ip_but_keeps_method_headers_body_and_query() {
        let mut req = request(
            "https://198.18.0.148:443/connector/ws?fixture=1",
            "aga-alb.mahjong-jp.net",
        );
        let headers = req.headers().clone();
        assert!(restore(&mut req));
        assert_eq!(
            req.uri(),
            "https://aga-alb.mahjong-jp.net:443/connector/ws?fixture=1"
        );
        assert_eq!(req.headers(), &headers);
        assert_eq!(req.method(), Method::GET);
    }
    #[test]
    fn handles_other_half_of_fake_range_and_keeps_port() {
        let mut req = request(
            "http://198.19.255.254:8443/fixture",
            "AGA-ALB.MAHJONG-JP.NET",
        );
        assert!(restore(&mut req));
        assert_eq!(req.uri(), "http://aga-alb.mahjong-jp.net:8443/fixture");
    }
    #[test]
    fn excludes_connect_real_ips_and_other_domains() {
        for (uri, host) in [
            ("https://203.0.113.1:443/", "aga-alb.mahjong-jp.net"),
            ("https://aga-alb.mahjong-jp.net/", "aga-alb.mahjong-jp.net"),
            ("https://198.18.0.1/", "example.com"),
            ("https://198.18.0.1/", "evilmahjong-jp.net"),
            ("https://198.18.0.1/", "mahjong-jp.net.evil.example"),
            ("https://198.18.0.1:443/", "aga-alb.mahjong-jp.net:8443"),
        ] {
            let mut req = request(uri, host);
            let original = req.uri().clone();
            assert!(!restore(&mut req));
            assert_eq!(req.uri(), &original);
        }
        let mut req = Request::builder()
            .method(Method::CONNECT)
            .uri("198.18.0.1:443")
            .header(HOST, "aga-alb.mahjong-jp.net")
            .body(())
            .unwrap();
        assert!(!restore(&mut req));
    }
}
