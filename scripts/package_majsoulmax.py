"""Allowlist the Rust MajsoulMax component, including corresponding GPL source."""
import shutil
from pathlib import Path
FILES=[
"majsoulmax-worker.exe","Cargo.toml","Cargo.lock","build.rs","LICENSE","README.md","SOURCE.json",
"src/main.rs","src/modder.rs","src/parser.rs","src/settings.rs","src/proto/mod.rs","src/proto/base.rs",
"liqi_config/liqi.desc","liqi_config/liqi.json","liqi_config/max_data.yaml",
"liqi_config/max_data.local.json","liqi_config/settings.json","liqi_config/settings.mod.json"]
def copy_native(source,destination):
    for name in FILES:
        origin=source/name
        if not origin.is_file():raise ValueError("Build the Rust worker and include its source: "+str(origin))
        target=destination/name
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(origin,target)
