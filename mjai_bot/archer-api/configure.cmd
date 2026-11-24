@echo off
setlocal
cd /d "%~dp0"
if exist "..\..\runtime\python\x86_64-pc-windows-msvc\pythonw.exe" (
  start "" "..\..\runtime\python\x86_64-pc-windows-msvc\pythonw.exe" "%~dp0configure.py"
  exit /b
)
if exist "..\..\runtime\python\x86_64-pc-windows-msvc\python.exe" (
  "..\..\runtime\python\x86_64-pc-windows-msvc\python.exe" "%~dp0configure.py"
  exit /b
)
if exist ".akagi\venv\Scripts\pythonw.exe" (
  start "" ".akagi\venv\Scripts\pythonw.exe" "%~dp0configure.py"
  exit /b
)
py -3 "%~dp0configure.py"
