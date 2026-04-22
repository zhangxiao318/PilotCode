@echo off
REM PilotCode launcher script for Windows
REM Usage: pilotcode [command] [args...]
REM        pilotcode           # Start main application
REM        pilotcode --tui     # Start TUI mode
REM        pilotcode configure # Run configuration wizard

REM Prevent "Terminate batch job" prompt on Ctrl+C
SETLOCAL EnableExtensions
IF ERRORLEVEL 1 (
    echo ERROR: Unable to enable extensions
    exit /b 1
)

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
python -m pilotcode %*

REM Exit with Python's exit code
EXIT /B %ERRORLEVEL%
