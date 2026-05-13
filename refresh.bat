@echo off
REM ============================================================
REM PSI Cash Flow Dashboard - One-Click Refresh (Windows)
REM ============================================================
setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "LOGFILE=%~dp0refresh.log"

echo. > "%LOGFILE%"
call :LOG "===================================================="
call :LOG "  PSI CASH FLOW DASHBOARD - REFRESH"
call :LOG "  %DATE% %TIME%"
call :LOG "===================================================="
call :LOG ""

REM --- 1. Detect Python (verify it actually works, not just stub) ---
set "PY="
REM Try `python` first - but verify it's not the Microsoft Store stub
where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys; sys.exit(0)" >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
REM Fallback to `py` (Python Launcher, bypasses MS Store stub)
if not defined PY (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -c "import sys; sys.exit(0)" >nul 2>nul
        if not errorlevel 1 set "PY=py -3"
    )
)
REM Last resort: python3
if not defined PY (
    where python3 >nul 2>nul
    if not errorlevel 1 (
        python3 -c "import sys; sys.exit(0)" >nul 2>nul
        if not errorlevel 1 set "PY=python3"
    )
)

if not defined PY (
    call :LOG "[ERROR] Python tidak ditemukan / tidak bisa dijalankan."
    call :LOG ""
    call :LOG "Penyebab umum: Microsoft Store stub mengintercept command 'python'."
    call :LOG "Solusi:"
    call :LOG "  1. Buka Settings - Apps - Advanced app settings"
    call :LOG "     - App execution aliases"
    call :LOG "  2. Matikan toggle 'python.exe' dan 'python3.exe'"
    call :LOG "  3. Tutup Command Prompt, buka baru"
    call :LOG "  4. Ketik 'python --version' untuk verify"
    call :LOG "  5. Klik refresh.bat lagi"
    goto :ERROR_END
)

call :LOG "[INFO] Python detected: %PY%"
%PY% --version >> "%LOGFILE%" 2>&1

REM --- 2. Check Excel is closed ---
if exist "~$PSI Cash Monitoring Master.xlsx" (
    call :LOG ""
    call :LOG "[ERROR] File Excel masih TERBUKA. Tutup dulu lalu coba lagi."
    goto :ERROR_END
)

REM --- 3. Ensure required packages are installed ---
call :LOG ""
call :LOG "[1/4] Cek packages (openpyxl, cryptography) ..."
%PY% -c "import openpyxl, cryptography" >nul 2>nul
if errorlevel 1 (
    call :LOG "      Installing packages ..."
    %PY% -m pip install --quiet --upgrade pip >> "%LOGFILE%" 2>&1
    %PY% -m pip install --quiet -r scripts\requirements.txt >> "%LOGFILE%" 2>&1
    if errorlevel 1 (
        call :LOG "[ERROR] Gagal install package. Lihat refresh.log"
        goto :ERROR_END
    )
    call :LOG "      Packages berhasil di-install."
) else (
    call :LOG "      Packages sudah terinstall."
)

REM --- 3b. Check / setup password file ---
set "PWFILE=%~dp0dashboard-password.txt"
if not exist "%PWFILE%" goto :NEED_PASSWORD
for %%I in ("%PWFILE%") do if %%~zI LEQ 1 goto :NEED_PASSWORD
goto :PASSWORD_OK

:NEED_PASSWORD
call :LOG ""
call :LOG "===================================================="
call :LOG "  SETUP PASSWORD DASHBOARD (sekali saja)"
call :LOG "===================================================="
echo.
echo File dashboard-password.txt belum ada atau kosong.
echo Masukkan password untuk dashboard:
echo.
set /p NEW_PW="Password: "
if "!NEW_PW!"=="" (
    call :LOG "[ERROR] Password kosong, tidak bisa lanjut."
    goto :ERROR_END
)
> "%PWFILE%" echo !NEW_PW!
call :LOG "      Password tersimpan di dashboard-password.txt"
set "NEW_PW="

:PASSWORD_OK

REM --- 4. Run the refresh script ---
call :LOG ""
call :LOG "[2/4] Refresh CF Summary + Bank sheets + data.json ..."
%PY% scripts\refresh_dashboard.py >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    call :LOG "[ERROR] Script Python gagal. Lihat refresh.log untuk detail."
    goto :ERROR_END
)
call :LOG "      OK - sheets dan data.json updated."

REM --- 5. Verify outputs ---
if not exist "public\data.json" (
    call :LOG "[ERROR] public\data.json tidak terbuat."
    goto :ERROR_END
)

REM --- 6. Git commit and push ---
if not exist ".git" (
    call :LOG ""
    call :LOG "[INFO] Belum ada Git repo - skip push."
    goto :SUCCESS_END
)

call :LOG ""
call :LOG "[3/4] Git: stage + commit ..."
git add public/ scripts/ vercel.json README.md .gitignore refresh.bat refresh.sh setup-git.bat view.bat >> "%LOGFILE%" 2>&1

set "stamp=%DATE% %TIME:~0,5%"
git commit -m "Refresh dashboard %stamp%" >> "%LOGFILE%" 2>&1

call :LOG "[4/4] Git: push ..."
git push >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    call :LOG "[INFO] Plain git push gagal. Mencoba dengan --set-upstream ..."
    git push --set-upstream origin main >> "%LOGFILE%" 2>&1
    if errorlevel 1 (
        call :LOG "[WARN] git push gagal. Lihat refresh.log."
    ) else (
        call :LOG "      OK - push berhasil dengan upstream tracking."
    )
)

:SUCCESS_END
call :LOG ""
call :LOG "===================================================="
call :LOG "  SELESAI"
call :LOG "===================================================="
call :LOG ""
echo Buka URL Vercel atau public\index.html untuk lihat dashboard.
echo.
pause
exit /b 0

:ERROR_END
call :LOG ""
call :LOG "===================================================="
call :LOG "  GAGAL. Detail di refresh.log"
call :LOG "===================================================="
echo.
echo Buka refresh.log untuk lihat error.
echo.
pause
exit /b 1

:LOG
echo %~1
echo %~1 >> "%LOGFILE%"
goto :eof
