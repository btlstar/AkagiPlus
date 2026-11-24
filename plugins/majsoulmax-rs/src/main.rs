// SPDX-License-Identifier: GPL-3.0-only
//! AkagiPlus JSONL adapter for the user's MajsoulMax-rs core.
mod modder;
mod parser;
mod proto;
mod settings;

use anyhow::{Context, Result, ensure};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use bytes::Bytes;
use modder::Modder;
use parser::Parser;
use serde_json::{json, Value};
use settings::{MaxData, ModSettings, Settings};
use std::{collections::HashMap, io::{self, BufRead, Write}, path::PathBuf};
use tokio::sync::RwLock;

pub(crate) const ARBITRARY_MD5: &str = "0123456789abcdef0123456789abcdef";
const MAX_LINE: usize = 12 * 1024 * 1024;

struct Worker {
    settings: &'static Settings,
    modder: Modder,
    flows: HashMap<String, Parser>,
}
impl Worker {
    async fn new() -> Result<Self> {
        let base = std::env::current_exe()?.parent().context("executable directory")?.join("liqi_config");
        let root = PathBuf::from(std::env::var_os("AKAGIPLUS_MAJSOULMAX_DATA_DIR").context("private data directory required")?);
        let private = root.join("rust");
        std::fs::create_dir_all(&private)?;
        for name in ["liqi.desc", "liqi.json", "max_data.yaml", "max_data.local.json", "settings.json"] {
            std::fs::copy(base.join(name), private.join(name))?;
        }
        let settings = Box::leak(Box::new(Settings::new(&private)?));
        let choices = ModSettings::new(settings)?;
        let data = MaxData::load(&private)?;
        let modder = Modder::new(RwLock::new(choices), data).await?;
        Ok(Self {settings, modder, flows:HashMap::new()})
    }
    async fn handle(&mut self, request: Value) -> Result<Value> {
        let flow = request["flow"].as_str().context("flow required")?;
        ensure!(flow.len() <= 128, "flow too long");
        if request["op"] == "close" {
            self.flows.remove(flow);
            return Ok(json!({"closed":true}));
        }
        ensure!(request["op"] == "frame", "invalid operation");
        let from_client = request["from_client"].as_bool().context("direction required")?;
        let encoded = request["data"].as_str().context("data required")?;
        let raw = STANDARD.decode(encoded)?;
        let unchanged = json!({"data":encoded,"drop":false,"inject_client":[]});
        if raw.is_empty() || !matches!(raw[0],1..=3) || (raw[0] != 1 && raw.len()<3) {
            return Ok(unchanged);
        }
        if (raw[0] == 2 && !from_client) || (raw[0] == 3 && from_client) {
            return Ok(unchanged);
        }
        if !self.flows.contains_key(flow) {
            ensure!(self.flows.len()<32, "flow limit");
            self.flows.insert(flow.to_string(), Parser::new(&self.settings.proto_json,&self.settings.desc));
        }
        let parser = self.flows.get_mut(flow).expect("flow inserted");
        if raw[0]==3 {
            let id = u16::from_le_bytes([raw[1],raw[2]]) as usize;
            if !parser.respond_type.contains_key(&id) { return Ok(unchanged); }
        }
        let buffer = Bytes::from(raw);
        let parsed = match parser.parse(buffer.clone()) {
            Ok(parsed) => parsed,
            Err(_) => return Ok(unchanged),
        };
        let result = self.modder.modify(buffer,from_client,parsed.method_name).await;
        let injected = result.inject_msg.map(|msg|vec![STANDARD.encode(msg)]).unwrap_or_default();
        Ok(json!({"data":result.msg.as_ref().map(|msg|STANDARD.encode(msg)).unwrap_or_else(||encoded.to_string()),
                  "drop":result.msg.is_none(),"inject_client":injected}))
    }
}

#[tokio::main(flavor="multi_thread",worker_threads=2)]
async fn main() -> Result<()> {
    // stdout is reserved for protocol JSON. No HTTP listener, proxy, certificate or AI client.
    let mut worker = match Worker::new().await {
        Ok(worker)=>worker,
        Err(_)=>{println!("{}",json!({"ready":false,"error":"initialization_failed"}));return Ok(());}
    };
    let stdin=io::stdin();
    let mut output=io::BufWriter::new(io::stdout().lock());
    writeln!(output,"{}",json!({"ready":true,"protocol":1,"snapshot":"MajsoulMax-rs 0.7.0 / 0.16.293-4.0.51"}))?;
    output.flush()?;
    for line in stdin.lock().lines() {
        let line=line?;
        ensure!(line.len()<=MAX_LINE,"request too large");
        let response=match serde_json::from_str(&line) {
            Ok(request)=>worker.handle(request).await.unwrap_or_else(|_|json!({"error":"frame_rejected"})),
            Err(_)=>json!({"error":"invalid_json"}),
        };
        writeln!(output,"{response}")?;
        output.flush()?;
    }
    Ok(())
}
