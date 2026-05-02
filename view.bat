@echo off
REM ============================================================
REM PSI Cash Flow Dashboard - Local Preview
REM ============================================================
REM Opens the dashboard via a small local web server.
REM Use this if double-clicking index.html does not work.
REM ============================================================
setlocal
cd /d "%~dp0\public"

REM Detect Python
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY ( where py >nul 2>nul && set "PY=py -3" )
if not defined PY ( where python3 >nul 2>nul && set "PY=python3" )
if not defined PY (
    echo [ERROR] Python tidak ditemukan. Install Python dulu, atau coba double-click index.html.
    pause
    exit /b 1
)

echo.
echo Membuka dashboard di browser ^(http://localhost:8765^) ...
echo Tutup jendela ini untuk menghentikan server.
echo.

REM Open browser after 1 second
start "" cmd /c "timeout /t 1 /nobreak >nul && start http://localhost:8765"

%PY% -m http.server 8765
