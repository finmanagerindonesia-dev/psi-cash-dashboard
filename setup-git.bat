@echo off
REM ============================================================
REM PSI Cash Flow Dashboard - First-Time Git Setup
REM ============================================================
REM Sekali jalankan ini untuk push file lokal ke GitHub repo.
REM Setelah itu, pakai refresh.bat untuk update harian.
REM ============================================================
setlocal
cd /d "%~dp0"

set "REPO_URL=https://github.com/finmanagerindonesia-dev/psi-cash-dashboard.git"

echo.
echo ====================================================
echo   FIRST-TIME GIT SETUP
echo ====================================================
echo   Repo: %REPO_URL%
echo ====================================================
echo.

REM Check Git installed
where git >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Git tidak ditemukan. Install dulu dari:
    echo         https://git-scm.com/download/win
    pause
    exit /b 1
)

REM Check sudah ada .git folder?
if exist ".git" (
    echo [INFO] Git repo sudah ter-initialize di folder ini.
    echo        Kalau remote belum di-set, akan ditambahkan sekarang.
    git remote remove origin >nul 2>nul
    git remote add origin %REPO_URL%
    echo.
    echo Remote 'origin' sudah ter-set ke:
    git remote -v
    echo.
    pause
    exit /b 0
)

REM Initialize
echo [1/5] Initialize git repo ...
git init
if errorlevel 1 goto :ERROR

echo.
echo [2/5] Set default branch to 'main' ...
git branch -M main

echo.
echo [3/5] Stage all project files ...
git add .gitignore vercel.json README.md refresh.bat refresh.sh view.bat setup-git.bat scripts/ public/

echo.
echo [4/5] Make first commit ...
git -c user.email="finmanager.indonesia@prasadseeds.com" -c user.name="PSI Finance" commit -m "Initial commit - PSI Cash Flow Dashboard"
if errorlevel 1 goto :ERROR

echo.
echo [5/5] Connect to GitHub remote and push ...
git remote add origin %REPO_URL%
echo.
echo Pushing ke GitHub. Anda mungkin akan diminta login.
echo Pakai username GitHub Anda + Personal Access Token sebagai password.
echo  (Generate token di: GitHub - Settings - Developer settings - Personal access tokens)
echo.
git push -u origin main
if errorlevel 1 goto :PUSH_ERROR

echo.
echo ====================================================
echo   SUKSES! File sudah di GitHub.
echo ====================================================
echo.
echo Selanjutnya:
echo   1. Buka https://vercel.com - login dengan GitHub
echo   2. Add New - Project - Import 'psi-cash-dashboard'
echo   3. Klik Deploy. Tunggu ~30 detik.
echo   4. Anda dapat URL seperti: https://psi-cash-dashboard.vercel.app
echo   5. Share URL itu ke bos.
echo.
echo Untuk update harian: cukup klik refresh.bat.
echo.
pause
exit /b 0

:ERROR
echo.
echo [ERROR] Step gagal. Lihat error di atas.
pause
exit /b 1

:PUSH_ERROR
echo.
echo [ERROR] Push gagal. Penyebab umum:
echo.
echo   1. Authentication error:
echo      GitHub butuh Personal Access Token (bukan password biasa).
echo      Cara buat token:
echo        - https://github.com/settings/tokens
echo        - Generate new token (classic) - centang scope 'repo'
echo        - Copy tokennya
echo        - Saat git minta password, paste token itu
echo.
echo   2. Repo tidak kosong di GitHub:
echo      Kalau Anda sudah klik 'creating a new file' atau add README
echo      di GitHub, repo jadi tidak kosong. Solusi:
echo        Ketik manual di Command Prompt (di folder ini):
echo          git pull origin main --allow-unrelated-histories
echo          git push -u origin main
echo.
echo   3. Repo URL salah:
echo      Cek %REPO_URL%
echo      Buka di browser - kalau 404, repo URL salah.
echo.
pause
exit /b 1
