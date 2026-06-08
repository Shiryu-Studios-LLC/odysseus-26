@echo off
setlocal enabledelayedexpansion
title Shirabe Launcher (調べ)

cd /d "%~dp0"

if "%~1"=="--tunnel" goto :run_tunnel

echo ===================================================
echo   Shirabe Native Windows Launcher (調べ)
echo ===================================================
echo.

:: Default configuration
set BIND_HOST=127.0.0.1
set BIND_PORT=7000

:: Simple argument parsing
:parse_args
if "%~1"=="-h" goto :help
if "%~1"=="--help" goto :help
if "%~1"=="--host" (
    set BIND_HOST=%~2
    shift
    shift
    goto :parse_args
)
if "%~1"=="--port" (
    set BIND_PORT=%~2
    shift
    shift
    goto :parse_args
)
if not "%~1"=="" (
    echo Unknown argument: %~1
    goto :help
)
goto :args_done

:help
echo Usage: shirabe.cmd [--host HOST] [--port PORT]
echo.
echo Options:
echo   --host HOST    IP address to bind the server to (default: 127.0.0.1)
echo   --port PORT    Port to listen on (default: 7000)
echo.
exit /b 0

:args_done

:: 0. Check for Git updates (pull latest changes before launching)
where git >nul 2>nul
if errorlevel 1 (
    echo NOTE: Git command was not found on PATH. Skipping update check.
    goto :git_done
)

if not exist .git (
    echo NOTE: Not a git repository. Skipping update check.
    goto :git_done
)

echo ==^> Checking for updates...
git pull --ff-only
if not errorlevel 1 goto :git_success
echo WARNING: Git pull failed (you may be offline or have local changes).
echo          Continuing to launch Shirabe anyway...
goto :git_done

:git_success
echo Update check complete.

:git_done
echo.

:: 1. Locate a Python 3.11+ interpreter
echo ==^> Checking for Python 3.11+...

set PYTHON_EXE=

:: Check py launcher for python 3.11, 3.12, 3.13
for %%v in (3.13 3.12 3.11) do (
    py -%%v -c "import sys; print(sys.version)" >nul 2>nul
    if not errorlevel 1 (
        set PYTHON_EXE=py -%%v
        goto :found_python
    )
)

:: Check default python on PATH
python -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>nul
if not errorlevel 1 (
    set PYTHON_EXE=python
    goto :found_python
)

echo.
echo ERROR: Python 3.11+ was not found on your system.
echo Please install Python 3.11+ from https://www.python.org/downloads/
echo and make sure to check "Add Python to PATH" during installation.
echo.
pause
exit /b 1

:found_python
echo Using Python command: !PYTHON_EXE!

:: 2. Create the virtualenv if missing
if exist venv\Scripts\python.exe (
    echo venv already exists - skipping creation.
    goto :venv_done
)

echo.
echo ==^> Creating virtual environment...
!PYTHON_EXE! -m venv venv
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment.
    pause
    exit /b 1
)

:venv_done

:: 3. Install / update dependencies
echo.
echo ==^> Installing/updating dependencies...
venv\Scripts\python.exe -m pip install --upgrade pip --quiet
venv\Scripts\python.exe -m pip install -r app\requirements.txt
if errorlevel 1 (
    echo ERROR: Dependency installation failed.
    pause
    exit /b 1
)

:: 4. First-time setup (creates data dirs, DB, .env, admin user)
echo.
echo ==^> Running setup...
venv\Scripts\python.exe app\setup.py
if errorlevel 1 (
    echo ERROR: setup.py failed.
    pause
    exit /b 1
)

:: 5. Friendly check for Git Bash (Cookbook / agent-shell parity)
where bash >nul 2>nul
if errorlevel 1 (
    echo.
    echo NOTE: Git Bash [bash.exe] was not found on PATH.
    echo       The core app works without it. For full Cookbook background
    echo       downloads and the agent shell tool, install Git for Windows:
    echo       https://git-scm.com/download/win
)

:: 5.5. Start Cloudflare Tunnel automatically if configured in .env
if exist .env (
    set "HAS_TUNNEL="
    for /f "usebackq delims=" %%x in (".env") do (
        set "line=%%x"
        if "!line:~0,13!"=="TUNNEL_TOKEN=" (
            set "token_val=!line:~13!"
            if not "!token_val!"=="" set HAS_TUNNEL=1
        )
    )
    if defined HAS_TUNNEL (
        echo ==^> Starting Cloudflare Tunnel in background (hidden)...
        powershell -Command "Start-Process cmd -ArgumentList '/c shirabe.cmd --tunnel' -WindowStyle Hidden"
    )
)

:: 6. Start the server
echo.
echo ==^> Starting Shirabe at http://!BIND_HOST!:!BIND_PORT!
echo Press Ctrl+C to stop.
echo.
venv\Scripts\python.exe -m uvicorn app.app:app --host !BIND_HOST! --port !BIND_PORT!
set EXIT_CODE=%errorlevel%

:: Stop Cloudflare Tunnel if it was started
taskkill /f /im cloudflared.exe >nul 2>nul

if %EXIT_CODE% neq 0 (
    echo.
    echo ERROR: Shirabe failed to start or exited with an error.
    pause
    exit /b %EXIT_CODE%
)
echo.
echo Shirabe server has shut down.
pause
exit /b 0

:run_tunnel
title Shirabe Cloudflare Tunnel (調べ)
echo ===================================================
echo   Shirabe Cloudflare Tunnel (調べ) Native Launcher
echo ===================================================
echo.

:: 1. Parse TUNNEL_TOKEN from .env
set TUNNEL_TOKEN=
for /f "usebackq delims=" %%x in (".env") do (
    set "line=%%x"
    if "!line:~0,13!"=="TUNNEL_TOKEN=" (
        set "TUNNEL_TOKEN=!line:~13!"
    )
)

:: Trim spaces or quotes if any
if not "!TUNNEL_TOKEN!"=="" (
    for /f "tokens=* delims= " %%a in ("!TUNNEL_TOKEN!") do set TUNNEL_TOKEN=%%a
)

if "!TUNNEL_TOKEN!"=="" (
    echo ERROR: TUNNEL_TOKEN is not configured in your .env file.
    echo.
    echo Please open the .env file in the root directory, locate
    echo the TUNNEL_TOKEN= line under the Cloudflare section,
    echo set it to your Cloudflare Tunnel Token, and restart this script.
    echo.
    pause
    exit /b 1
)

:: 2. Check for cloudflared command
where cloudflared >nul 2>nul
if errorlevel 1 (
    :: Try standard installations
    if exist "C:\Program Files (x86)\cloudflared\cloudflared.exe" (
        set CLOUDFLARED_EXE="C:\Program Files (x86)\cloudflared\cloudflared.exe"
    ) else if exist "C:\Program Files\cloudflared\cloudflared.exe" (
        set CLOUDFLARED_EXE="C:\Program Files\cloudflared\cloudflared.exe"
    ) else (
        echo ERROR: cloudflared was not found on PATH or in standard install locations.
        echo Please download and install the Cloudflare Tunnel daemon:
        echo https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
        echo.
        pause
        exit /b 1
    )
) else (
    set CLOUDFLARED_EXE=cloudflared
)

echo ==^> Starting Cloudflare Tunnel...
echo Using token prefix: !TUNNEL_TOKEN:~0,10!***************************
echo.

!CLOUDFLARED_EXE! tunnel run --token !TUNNEL_TOKEN!
if errorlevel 1 (
    echo.
    echo ERROR: Cloudflare Tunnel exited with an error.
    pause
    exit /b !errorlevel!
)
echo.
echo Tunnel closed.
pause
exit /b 0

