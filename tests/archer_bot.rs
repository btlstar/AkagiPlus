//! Verify the Archer adapter through Akagi's actual subprocess runner.
use akagi::bot::{BotRunner, Manifest, PythonRuntime, RuntimeMode, SubprocessBot};
use akagi::schema::MjaiEvent;
use serde_json::{json, Value};
use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpListener;
use std::path::PathBuf;
use std::time::{Duration, Instant};
use tokio::process::Command;

#[tokio::test]
async fn archer_manifest_runner_reach_scores_and_usage() {
    run_case(4).await;
}
#[tokio::test]
async fn archer_manifest_runner_sanma_north_and_usage() {
    run_case(3).await;
}
async fn run_case(players: u8) {
    let root = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let bot_dir = root.join("mjai_bot/archer-api");
    let manifest = Manifest::load(&bot_dir).unwrap().expect("Archer manifest");
    assert_eq!(manifest.bot.supported_modes, ["4p", "3p"]);
    assert!(manifest.settings["api_key"].secret);
    let python = std::env::var_os("ARCHER_TEST_PYTHON")
        .map(PathBuf::from)
        .unwrap_or_else(|| root.join("runtime/python/x86_64-pc-windows-msvc/python.exe"));
    assert!(
        python.is_file(),
        "Set ARCHER_TEST_PYTHON to a Python 3.12+ interpreter"
    );
    let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
    let port = listener.local_addr().unwrap().port();
    listener.set_nonblocking(true).unwrap();
    let service = std::thread::spawn(move || {
        let deadline = Instant::now() + Duration::from_secs(8);
        let mut stream = loop {
            match listener.accept() {
                Ok((stream, _)) => break stream,
                Err(error) if error.kind() == std::io::ErrorKind::WouldBlock => {
                    assert!(
                        Instant::now() < deadline,
                        "adapter did not call the fixture server"
                    );
                    std::thread::sleep(Duration::from_millis(10));
                }
                Err(error) => panic!("{error}"),
            }
        };
        stream.set_nonblocking(false).unwrap();
        stream
            .set_read_timeout(Some(Duration::from_secs(4)))
            .unwrap();
        let mut reader = BufReader::new(stream.try_clone().unwrap());
        let mut first = String::new();
        reader.read_line(&mut first).unwrap();
        assert!(first.starts_with("POST /v1/decide "));
        let mut length = 0;
        loop {
            let mut line = String::new();
            reader.read_line(&mut line).unwrap();
            if line == "\r\n" {
                break;
            }
            if let Some(value) = line.to_ascii_lowercase().strip_prefix("content-length:") {
                length = value.trim().parse::<usize>().unwrap();
            }
        }
        let mut body = vec![0; length];
        reader.read_exact(&mut body).unwrap();
        let request: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(request["seat"], 0);
        assert_eq!(request["events"][0]["type"], "start_kyoku");
        assert!(!request.to_string().contains("_ap_legal_actions"));
        assert_eq!(
            request["model"],
            if players == 3 {
                "fixture-3p"
            } else {
                "fixture-4p"
            }
        );
        assert_eq!(
            request["events"][0]["scores"].as_array().unwrap().len(),
            players as usize
        );
        let response = if players==3 {json!({"action":{"type":"nuki","actor":0},"candidates":[{"type":"nuki","q":8.211}],"usage":{"input_tokens":102,"output_tokens":42,"billed_tokens":183,"balance":999817}})} else {json!({
            "action":{"type":"reach","actor":0},
            "next":{"type":"dahai","actor":0,"pai":"P","tsumogiri":false},
            "candidates":[{"type":"reach","q":8.211},{"type":"dahai","pai":"P","q":7.804}],
            "usage":{"input_tokens":102,"output_tokens":42,"billed_tokens":183,"balance":999817}
        })}.to_string();
        write!(stream, "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}", response.len(), response).unwrap();
    });
    let temporary = tempfile::TempDir::new().unwrap();
    let configuration = temporary.path().join("config.json");
    std::fs::write(&configuration, json!({
        "api_url":format!("http://127.0.0.1:{port}"),"api_key":"fixture-key",
        "model":"fixture-4p","model_3p":"fixture-3p","score_mode":"weights","timeout_ms":3000,"top_n":5,"proxy_url":""
    }).to_string()).unwrap();
    let mut command = Command::new(&python);
    command
        .current_dir(&bot_dir)
        .args(["bot.py", "0"])
        .env("AKAGI_BOT_CONFIG", &configuration);
    let runtime = PythonRuntime::from_paths(python, PathBuf::from("unused"), RuntimeMode::System);
    let mut runner = SubprocessBot::spawn_with_command(
        command,
        runtime,
        &bot_dir,
        0,
        akagi::event_bus::notify_bus(),
    )
    .await
    .unwrap();
    let hand = if players == 3 {
        json!(["1p", "2p", "3p", "5p", "5pr", "7p", "8p", "9p", "2s", "3s", "E", "E", "N"])
    } else {
        json!(["1m", "2m", "3m", "5m", "5mr", "7p", "8p", "9p", "2s", "3s", "E", "E", "P"])
    };
    let hidden = json!(vec!["?"; 13]);
    let hands: Vec<Value> = (0..players)
        .map(|seat| {
            if seat == 0 {
                hand.clone()
            } else {
                hidden.clone()
            }
        })
        .collect();
    let scores = vec![if players == 3 { 35000 } else { 25000 }; players as usize];
    let names = vec!["fixture"; players as usize];
    let events = json!([
        {"type":"start_game","names":names,"id":0,"num_players":players},
        {"type":"start_kyoku","bakaze":"E","dora_marker":"2s","kyoku":1,"honba":0,"kyotaku":0,
         "oya":0,"scores":scores,"tehais":hands,"num_players":players},
        {"type":"tsumo","actor":0,"pai":"4s"}
    ]);
    let batch: Vec<MjaiEvent> = serde_json::from_value(events).unwrap();
    let reply = runner
        .react_with_legal_actions(&batch, Some(&[json!({"type":"dahai","pai":"4s"})]))
        .await
        .unwrap();
    if players == 3 {
        assert!(matches!(reply.action, MjaiEvent::Kita { actor: 0, .. }));
    } else {
        assert!(
            matches!(reply.action, MjaiEvent::Reach { actor:0, pai:Some(ref tile) } if tile == "P")
        );
    }
    let meta = reply.meta.unwrap();
    assert_eq!(meta["archer"]["billed_tokens"], 183);
    let rows = meta["show"]["items"].as_array().unwrap();
    assert_eq!(
        rows.iter()
            .map(|row| (row["weight_percent"].as_f64().unwrap() * 10.0).round() as u64)
            .sum::<u64>(),
        1000
    );
    assert!(rows
        .iter()
        .all(|row| row["value"].as_str().unwrap().ends_with('%') && row.get("note").is_none()));
    if players == 4 {
        let follow = runner
            .react(&[serde_json::from_value(json!({"type":"reach","actor":0})).unwrap()])
            .await
            .unwrap();
        assert!(matches!(follow.action, MjaiEvent::Dahai { actor: 0, .. }));
        let forced: Vec<MjaiEvent> = serde_json::from_value(json!([
            {"type":"dahai","actor":0,"pai":"P","tsumogiri":false},
            {"type":"reach_accepted","actor":0},
            {"type":"tsumo","actor":1,"pai":"?"},
            {"type":"dahai","actor":1,"pai":"C","tsumogiri":true},
            {"type":"tsumo","actor":0,"pai":"9s"}
        ]))
        .unwrap();
        let local = runner
            .react_with_legal_actions(&forced, Some(&[json!({"type":"dahai","pai":"9s"})]))
            .await
            .unwrap();
        assert!(
            matches!(local.action, MjaiEvent::Dahai {actor:0, tsumogiri:true, ref pai} if pai=="9s")
        );
        let meta = local.meta.unwrap();
        assert_eq!(meta["archer"]["calls"], 1);
        assert_eq!(meta["archer"]["skipped_requests"], 1);
    }
    let end = runner
        .react(&[serde_json::from_value(json!({"type":"end_game"})).unwrap()])
        .await
        .unwrap();
    assert!(matches!(end.action, MjaiEvent::None));
    service.join().unwrap();
}
