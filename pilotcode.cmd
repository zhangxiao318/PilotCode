@echo off
REM PilotCode launcher script for Windows
REM Usage: pilotcode [command] [args...]
REM        pilotcode           # Start main application
REM        pilotcode --tui     # Start TUI mode
REM        pilotcode configure # Run configuration wizard

chcp 65001 >nul

REM Set UTF-8 encoding for proper international character support
set PYTHONIOENCODING=utf-8

REM Get script directory (for PYTHONPATH)
set "SCRIPT_DIR=%~dp0"

REM Set PYTHONPATH to include src directory
set "PYTHONPATH=%SCRIPT_DIR%src;%PYTHONPATH%"

REM Check if virtual environment exists and activate it
if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

REM Run PilotCode
if "%~1"=="" (
    REM No arguments: start main application (default)
    python -m pilotcode
) else (
    set "FIRST_ARG=%~1"
    setlocal EnableDelayedExpansion
    if "!FIRST_ARG:~0,2!"=="--" (
        REM Arguments start with -- (options): treat as 'main' command with options
        python -m pilotcode %*
    ) else (
        REM Arguments start with a command: pass through as-is
        python -m pilotcode %*
    )
    endlocal
)
