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

REM --- 1. Detect Python ---
set "PY="
where python >nul 2>nul && set "PY=python"
if not defined PY (
    where py >nul 2>nul && set "PY=py -3"
)
if not defined PY (
    where python3 >nul 2>nul && set "PY=python3"
)

if not defined PY (
    call :LOG "[ERROR] Python tidak ditemukan di PATH."
    call :LOG ""
    call :LOG "Cara fix:"
    call :LOG "  1. Buka Command Prompt"
    call :LOG "  2. Ketik: python --version"
    call :LOG "     atau:  py --version"
    call :LOG "  3. Kalau salah satu jalan, kasih tahu hasilnya."
    call :LOG ""
    call :LOG "Kemungkinan: saat install Python, kotak"
    call :LOG "'Add Python to PATH' tidak dicentang."
    call :LOG "Solusi: Reinstall Python dan centang 'Add Python to PATH',"
    call :LOG "atau install via Microsoft Store (otomatis terdaftar di PATH)."
    goto :ERROR_END
)

call :LOG "[INFO] Python detected: %PY%"
%PY% --version >> "%LOGFILE%" 2>&1

REM --- 2. Check Excel is closed ---
if exist "~$PSI Cash Monitoring Master.xlsx" (
    call :LOG ""
    call :LOG "[ERROR] File Excel masih TERBUKA di Excel."
    call :LOG "        Tolong tutup 'PSI Cash Monitoring Master.xlsx' di Excel"
    call :LOG "        kemudian klik refresh.bat lagi."
    goto :ERROR_END
)

REM --- 3. Ensure required packages are installed ---
call :LOG ""
call :LOG "[1/4] Cek packages (openpyxl, cryptography) ..."
%PY% -c "import openpyxl, cryptography" >nul 2>nul
if errorlevel 1 (
    call :LOG "      Package belum terinstall. Installing ..."
    %PY% -m pip install --quiet --upgrade pip >> "%LOGFILE%" 2>&1
    %PY% -m pip install --quiet -r scripts\requirements.txt >> "%LOGFILE%" 2>&1
    if errorlevel 1 (
        call :LOG "[ERROR] Gagal install package. Lihat detail di refresh.log"
        goto :ERROR_END
    )
    call :LOG "      Packages berhasil di-install."
) else (
    call :LOG "      Packages sudah terinstall."
)

REM --- 4. Run the refresh script ---
call :LOG ""
call :LOG "[2/4] Refresh CF Summary + Bank sheets + data.json ..."
%PY% scripts\refresh_dashboard.py >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    call :LOG ""
    call :LOG "[ERROR] Script Python gagal. Lihat refresh.log untuk detail."
    type "%LOGFILE%" | find /v "" /c >nul
    goto :ERROR_END
)
call :LOG "      OK - sheets dan data.json updated."

REM --- 5. Verify outputs ---
if not exist "public\data.json" (
    call :LOG "[ERROR] public\data.json tidak terbuat."
    goto :ERROR_END
)
if not exist "public\index.html" (
    call :LOG "[WARN]  public\index.html tidak ada (tapi data.json ada)."
)

REM --- 6. Git commit and push (only if a Git repo) ---
if not exist ".git" (
    call :LOG ""
    call :LOG "[INFO] Belum ada Git repo - skip push ke Vercel."
    call :LOG "       Untuk setup Git + Vercel, buka README.md."
    goto :SUCCESS_END
)

call :LOG ""
call :LOG "[3/4] Git: stage + commit ..."
git add public/ scripts/ vercel.json README.md .gitignore refresh.bat refresh.sh >> "%LOGFILE%" 2>&1

for /f "tokens=2 delims==" %%a in ('wmic OS Get localdatetime /value 2^>nul') do set "dt=%%a"
set "stamp=%dt:~0,4%-%dt:~4,2%-%dt:~6,2% %dt:~8,2%:%dt:~10,2%"
git commit -m "Refresh dashboard %stamp%" >> "%LOGFILE%" 2>&1

call :LOG "[4/4] Git: push ..."
git push >> "%LOGFILE%" 2>&1
if errorlevel 1 (
    call :LOG "[WARN]  git push gagal (mungkin remote belum di-set)."
    call :LOG "        Lihat refresh.log untuk detail."
)

:SUCCESS_END
call :LOG ""
call :LOG "===================================================="
call :LOG "  SELESAI."
call :LOG "  - Excel: PSI Cash Monitoring Master.xlsx (refreshed)"
call :LOG "  - Dashboard: public\index.html"
call :LOG "  - Data:      public\data.json"
call :LOG "===================================================="
call :LOG ""
echo Buka public\index.html di browser untuk lihat dashboard.
echo Atau, kalau Git+Vercel sudah ter-setup, tunggu ~30 detik.
echo.
pause
exit /b 0

:ERROR_END
call :LOG ""
call :LOG "===================================================="
call :LOG "  GAGAL. Detail tersimpan di: refresh.log"
call :LOG "===================================================="
echo.
echo Tolong screenshot atau copy isi file refresh.log
echo lalu kirim ke saya untuk diagnosa lebih lanjut.
echo.
pause
exit /b 1

:LOG
echo %~1
echo %~1 >> "%LOGFILE%"
goto :eof
