param([switch]$PackageOnly)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath (Split-Path -Parent $PSScriptRoot)
$tools = if ($env:AKAGIPLUS_DEVTOOLS) { $env:AKAGIPLUS_DEVTOOLS } else { 'D:\DevTools' }
if (Test-Path -LiteralPath "$tools\cargo\bin\cargo.exe") {
    $env:CARGO_HOME = "$tools\cargo"; $env:RUSTUP_HOME = "$tools\rustup"
    $env:PATH = "$tools\cargo\bin;" + $env:PATH
}
$node = Get-ChildItem -LiteralPath $tools -Directory -Filter 'node-*-win-x64' -ErrorAction SilentlyContinue | Sort-Object Name -Descending | Select-Object -First 1
if ($node) { $env:PATH = $node.FullName + ';' + $env:PATH }
if (-not $env:PROTOC -and (Test-Path -LiteralPath "$tools\protoc\bin\protoc.exe")) { $env:PROTOC = "$tools\protoc\bin\protoc.exe" }
$cmake = "$tools\BuildTools\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin"
if (Test-Path -LiteralPath $cmake) { $env:PATH = "$cmake;" + $env:PATH }
$env:CARGO_BUILD_JOBS = '4'
if (-not $PackageOnly) {
    Push-Location frontend
    try { & npm.cmd run build; if ($LASTEXITCODE -ne 0) { throw 'Frontend build failed' } } finally { Pop-Location }
    & cargo build --release --features custom-protocol --locked
    if ($LASTEXITCODE -ne 0) { throw 'Release build failed' }
}
$python = '.\runtime\python\x86_64-pc-windows-msvc\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Prepare the pinned portable runtime first; see docs/RELEASE.md' }
& $python scripts/package-windows.py
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed' }
