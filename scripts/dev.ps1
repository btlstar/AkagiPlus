param([switch]$Check)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
# Optional local D-drive toolchain. No installation or global PATH changes.
$tools = if ($env:AKAGIPLUS_DEVTOOLS) { $env:AKAGIPLUS_DEVTOOLS } else { 'D:\DevTools' }
if (Test-Path -LiteralPath "$tools\cargo\bin\cargo.exe") {
    $env:CARGO_HOME = "$tools\cargo"
    $env:RUSTUP_HOME = "$tools\rustup"
    $env:PATH = "$tools\cargo\bin;" + $env:PATH
}
$node = Get-ChildItem -LiteralPath $tools -Directory -Filter 'node-*-win-x64' -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
if ($node) { $env:PATH = $node.FullName + ';' + $env:PATH }
$env:PATH = (Join-Path (Get-Location) '.venv\Scripts') + ';' + $env:PATH
# Resolve protoc before launching Vite or starting a costly Rust compilation.
if (-not $env:PROTOC) {
    foreach ($candidate in @((Join-Path (Get-Location) '.local\tools\protoc\bin\protoc.exe'), "$tools\protoc\bin\protoc.exe")) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            $env:PROTOC = (Resolve-Path -LiteralPath $candidate).ProviderPath
            break
        }
    }
    if (-not $env:PROTOC) {
        $systemProtoc = Get-Command protoc -ErrorAction SilentlyContinue
        if ($systemProtoc) { $env:PROTOC = $systemProtoc.Source }
    }
}
if (-not $env:PROTOC -or -not (Test-Path -LiteralPath $env:PROTOC -PathType Leaf)) {
    throw 'Missing protoc. Run .venv\Scripts\python.exe scripts\setup-protoc.py, then start.bat again.'
}
& $env:PROTOC --version
if ($LASTEXITCODE -ne 0) { throw 'protoc could not run. Reinstall it using scripts/setup-protoc.py.' }
$env:PATH = (Split-Path -Parent $env:PROTOC) + ';' + $env:PATH
if (Test-Path -LiteralPath "$tools\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin") {
    $env:PATH = "$tools\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin;" + $env:PATH
}
$env:CARGO_PROFILE_DEV_DEBUG = '0' 
$env:CARGO_BUILD_JOBS = '4'
$env:npm_config_cache = Join-Path $tools 'npm-cache'
foreach ($command in @('cargo', 'node', 'npm.cmd')) {
    if (-not (Get-Command $command -ErrorAction SilentlyContinue)) { throw "Missing $command. See docs/AKAGIPLUS.md; this launcher never installs tools automatically." }
}
if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) { throw 'MajsoulMax environment missing. Run: py -3.11 -m venv .venv, then .venv\Scripts\python -m pip install -r plugins/majsoulmax/requirements.txt' }
if (-not (Test-Path -LiteralPath 'frontend\node_modules\.bin\tauri.cmd')) { throw 'Frontend dependencies missing. Run npm ci in frontend first.' }
if ($Check) { Write-Output 'AkagiPlus source environment paths OK'; exit 0 }
New-Item -ItemType Directory -Path '.local' -Force | Out-Null
# Tauri needs two separators: runner args, then application args.
& '.\frontend\node_modules\.bin\tauri.cmd' dev -- -- --config .local/config.toml
exit $LASTEXITCODE
