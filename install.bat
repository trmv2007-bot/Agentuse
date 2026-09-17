@echo off
rem ═══════════════════════════════════════════════════════════════
rem  AGENTUSE — one-shot installer for Windows
rem  Double-click this file, or run from a terminal:
rem     git clone https://github.com/trmv2007-bot/Agentuse.git && cd Agentuse && install.bat
rem  Finds Python 3.10+, creates .venv, installs deps, boots the grid.
rem ═══════════════════════════════════════════════════════════════
setlocal enabledelayedexpansion
title AGENTUSE installer

rem ---- 1. locate the repo (clone if this file was downloaded alone) ----
if not exist run.py (
    echo [AGENTUSE] not inside the repo - cloning...
    where git >nul 2>nul || (
        echo [!] git is required. Install from https://git-scm.com/download/win
        pause & exit /b 1
    )
    if exist "%USERPROFILE%\Agentuse\.git" (
        cd /d "%USERPROFILE%\Agentuse"
    ) else (
        git clone --depth 1 https://github.com/trmv2007-bot/Agentuse.git "%USERPROFILE%\Agentuse" || (echo [!] clone failed & pause & exit /b 1)
        cd /d "%USERPROFILE%\Agentuse"
    )
)
echo [OK] repo: %CD%

rem ---- 2. find Python 3.10+ (py launcher preferred, then python) ----
set PY=
where py >nul 2>nul && (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul && set PY=py -3
)
if not defined PY (
    where python >nul 2>nul && (
        python -c "import sys; raise SystemExit(0 if sys.version_info>=(3,10) else 1)" >nul 2>nul && set PY=python
    )
)
if not defined PY (
    echo [!] Python 3.10+ not found. Install from https://www.python.org/downloads/
    echo     IMPORTANT: tick "Add python.exe to PATH" in the installer.
    pause & exit /b 1
)
for /f "tokens=*" %%v in ('%PY% --version 2^>^&1') do echo [OK] python: %%v

rem ---- 3. venv + dependencies ----
if not exist .venv (
    echo [AGENTUSE] creating virtual environment...
    %PY% -m venv .venv || (echo [!] venv creation failed & pause & exit /b 1)
)
set "VPY=.venv\Scripts\python.exe"
if not exist "%VPY%" (
    echo [!] venv python missing - unexpected. Delete .venv and rerun.
    pause & exit /b 1
)
echo [AGENTUSE] installing dependencies (fastapi, uvicorn, httpx, bs4, lxml)...
"%VPY%" -m pip install -q --upgrade pip
"%VPY%" -m pip install -q -r requirements.txt || (echo [!] dependency install failed & pause & exit /b 1)
echo [OK] dependencies installed

rem ---- 4. boot ----
echo.
echo   ====================================================
echo     A G E N T U S E  -  GRID COMING ONLINE
echo     SpaceGrid :  http://localhost:8000
echo     Close this window to take the grid offline
echo   ====================================================
echo.
"%VPY%" run.py
echo.
echo [i] grid exited. press any key to close.
pause >nul
