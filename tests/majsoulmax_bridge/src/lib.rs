// Compile the real bridge source without Tauri or any UI/toolchain downloads.
#[path = "../../../src/proxy/majsoulmax.rs"]
pub mod majsoulmax;

#[cfg(test)]
mod integration {
    use super::majsoulmax::{Flow, MajsoulMaxConfig, Worker};
    use std::path::PathBuf;

    fn root() -> PathBuf {
        PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
    }
    fn config(data: &std::path::Path) -> MajsoulMaxConfig {
        let root = root();
        MajsoulMaxConfig {
            enabled: true,
            python: root.join(if cfg!(windows) {
                ".venv/Scripts/python.exe"
            } else {
                ".venv/bin/python"
            }),
            worker: root.join("plugins/majsoulmax/worker.py"),
            data_dir: data.to_path_buf(),
        }
    }

    #[tokio::test]
    async fn real_worker_passthrough_and_rpc_flow_cleanup() {
        let temp = tempfile::tempdir().unwrap();
        let worker = Worker::start(&config(temp.path())).await.unwrap();
        let original = b"not liqi";
        let result = worker.transform("test", true, original).await.unwrap();
        assert_eq!(result.data, original);
        assert!(!result.drop);
        assert!(result.inject_client.is_empty());
        worker.close("test").await;
        drop(worker);
        assert!(temp.path().join("settings.mod.yaml").exists());
    }

    #[tokio::test]
    async fn malformed_frame_disables_worker_without_leaking_its_payload() {
        let temp = tempfile::tempdir().unwrap();
        let worker = Worker::start(&config(temp.path())).await.unwrap();
        let error = worker.transform("test", true, &[2]).await.err().unwrap();
        assert!(error.to_string().contains("rejected"));
        assert!(worker.transform("test", true, b"hello").await.is_err());
    }

    #[tokio::test]
    async fn worker_timeout_is_bounded_and_cannot_reuse_the_pipe() {
        let temp = tempfile::tempdir().unwrap();
        let script = temp.path().join("slow.py");
        std::fs::write(&script, "import sys,time\nprint('{\"ready\":true,\"protocol\":1}',flush=True)\nsys.stdin.readline()\ntime.sleep(10)\n").unwrap();
        let mut cfg = config(temp.path());
        cfg.worker = script;
        let worker = Worker::start(&cfg).await.unwrap();
        let start = std::time::Instant::now();
        let error = worker
            .transform("test", true, b"hello")
            .await
            .err()
            .unwrap();
        assert!(error.to_string().contains("timed out"));
        assert!(start.elapsed() < std::time::Duration::from_secs(2));
        assert!(worker.transform("test", true, b"again").await.is_err());
    }

    #[tokio::test]
    async fn injection_is_queued_until_client_relay_attaches() {
        let flow = Flow::new();
        flow.sender.try_send(vec![1, 2, 3]).unwrap();
        let mut receiver = flow.receiver.lock().unwrap().take().unwrap();
        assert_eq!(receiver.recv().await, Some(vec![1, 2, 3]));
        assert!(flow.receiver.lock().unwrap().is_none());
    }
}
