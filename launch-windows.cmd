@echo off
setlocal enabledelayedexpansion
title Odysseus Launcher

cd /d "%~dp0"

echo ===================================================
echo   Odysseus Native Windows Launcher
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
echo Usage: launch-windows.cmd [--host HOST] [--port PORT]
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
echo          Continuing to launch Odysseus anyway...
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
venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo ERROR: Dependency installation failed.
    pause
    exit /b 1
)

:: 4. First-time setup (creates data dirs, DB, .env, admin user)
echo.
echo ==^> Running setup...
venv\Scripts\python.exe setup.py
if errorlevel 1 (
    echo ERROR: setup.py failed.
    pause
    exit /b 1
)

:: 5. Friendly check for Git Bash (Cookbook / agent-shell parity)
where bash >nul 2>nul
if errorlevel 1 (
    echo.
    echo NOTE: Git Bash (bash.exe) was not found on PATH.
    echo       The core app works without it. For full Cookbook background
    echo       downloads and the agent shell tool, install Git for Windows:
    echo       https://git-scm.com/download/win
)

:: 6. Start the server
echo.
echo ==^> Starting Odysseus at http://!BIND_HOST!:!BIND_PORT!
echo Press Ctrl+C to stop.
echo.
venv\Scripts\python.exe -m uvicorn app:app --host !BIND_HOST! --port !BIND_PORT!
