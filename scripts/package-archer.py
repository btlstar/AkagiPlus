"""Build the standalone Archer bot archive; never include user configuration."""
from pathlib import Path
import argparse
import hashlib
import json
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = ("bot.py", "archer_client.py", "configure.py", "configure.cmd",
         "manifest.toml", "pyproject.toml", "README.md", "LICENSE.txt")


def build(output=None):
    source = ROOT / "mjai_bot" / "archer-api"
    manifest = tomllib.loads((source / "manifest.toml").read_text(encoding="utf-8"))
    version = manifest["bot"]["version"]
    output = Path(output) if output else ROOT / "dist" / ("archer-api-" + version) / "archer-api.zip"
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename in FILES:
            archive.write(source / filename, "archer-api/" + filename)
    with zipfile.ZipFile(output) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {"archer-api/" + name for name in FILES}
        assert tomllib.loads(archive.read("archer-api/manifest.toml").decode())["settings"]["api_key"]["default"] == ""
    return {"archive": str(output), "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
            "files": len(FILES), "version": version}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output")
    print(json.dumps(build(parser.parse_args().output), ensure_ascii=True, indent=2))
