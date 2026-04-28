@echo off
REM PilotCode Windows Installation Script

setlocal EnableDelayedExpansion

REM Parse command-line flags first
set "INSTALL_DEV=false"
set "INSTALL_INDEX=false"
set "INTERACTIVE=true"
:parse_args
if "%~1"=="--dev" (
    set "INSTALL_DEV=true"
    set "INTERACTIVE=false"
    shift
    goto parse_args
)
if "%~1"=="--index" (
    set "INSTALL_INDEX=true"
    set "INTERACTIVE=false"
    shift
    goto parse_args
)

echo ============================================
echo  PilotCode Windows Installer
echo ============================================
echo.

REM --- Check Python version ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.11+ first.
    echo         Download: https://www.python.org/downloads/
    echo         Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

for /f "tokens=2 delims= " %%a in ('python --version 2^>^&1') do set PYVER=%%a
for /f "tokens=1,2 delims=." %%a in ("%PYVER%") do (
    set PYMAJOR=%%a
    set PYMINOR=%%b
)

if %PYMAJOR% LSS 3 (
    echo [ERROR] Python %PYVER% is too old. Python 3.11+ required.
    pause
    exit /b 1
)
if %PYMAJOR%==3 if %PYMINOR% LSS 11 (
    echo [ERROR] Python %PYVER% is too old. Python 3.11+ required.
    pause
    exit /b 1
)

echo [OK] Python %PYVER% found.
echo(

REM --- Create virtual environment ---
set "VENV_DIR=%CD%\.venv"
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo [INFO] Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
) else (
    echo [OK] Virtual environment already exists.
)

REM --- Activate venv ---
call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
    echo [ERROR] Failed to activate virtual environment.
    pause
    exit /b 1
)

echo [OK] Virtual environment activated.
echo(

REM --- Upgrade pip ---
echo [INFO] Upgrading pip...
python -m pip install --upgrade pip
if errorlevel 1 (
    echo [WARN] pip upgrade failed, continuing with existing version...
)
echo(

REM --- Install core dependencies ---
echo [INFO] Installing PilotCode...
pip install -e .
if errorlevel 1 (
    echo [ERROR] Installation failed.
    pause
    exit /b 1
)
echo [OK] Core dependencies installed.
echo(

REM --- Copy knowhow templates ---
set "KNOWHOW_DIR=%USERPROFILE%\.pilotcode\data\knowhow"
if not exist "%KNOWHOW_DIR%\*.json" (
    if exist "config\knowhow\*.json" (
        echo [INFO] Copying default knowhow templates...
        if not exist "%KNOWHOW_DIR%" mkdir "%KNOWHOW_DIR%"
        copy /Y "config\knowhow\*.json" "%KNOWHOW_DIR%\" >nul 2>&1
        echo [OK] Knowhow templates copied.
    )
) else (
    echo [OK] Knowhow templates already exist.
)
echo(

REM --- Try to install tree-sitter C/C++ parsers ---
echo [INFO] Installing tree-sitter parsers for C/C++ code indexing...
pip install tree-sitter-c tree-sitter-cpp >nul 2>&1
if errorlevel 1 (
    echo(
    echo ============================================
    echo  [WARNING] Tree-sitter C/C++ parsers failed to install.
    echo ============================================
    echo(
    echo  This usually means a C compiler is not available.
    echo(
    echo  To enable C/C++ code indexing, install ONE of:
    echo    - Visual Studio Build Tools with C++ workload
    echo      https://visualstudio.microsoft.com/visual-cpp-build-tools/
    echo    - MinGW-w64 + MSYS2
    echo      https://www.msys2.org/
    echo    - LLVM/Clang
    echo(
    echo  PilotCode will still work fine --- C/C++ files will be
    echo  indexed using regex fallback ^(slightly less accurate^).
    echo(
    echo  You can re-run this installer later after installing a compiler.
    echo ============================================
    echo(
    pause
) else (
    echo [OK] Tree-sitter C/C++ parsers installed.
)
echo(

REM --- Optional: install dev dependencies ---
if "%INTERACTIVE%"=="true" (
    set /p INSTALL_DEV_REPLY="Install dev dependencies: pytest, black, ruff? [y/N]: "
    if /i "%INSTALL_DEV_REPLY%"=="y" set "INSTALL_DEV=true"
)
if "%INSTALL_DEV%"=="true" (
    echo [INFO] Installing dev dependencies...
    pip install -e ".[dev]"
    if errorlevel 1 (
        echo [WARN] Dev dependencies installation had issues.
    ) else (
        echo [OK] Dev dependencies installed.
    )
)
echo(

REM --- Optional: install extra language parsers ---
if "%INTERACTIVE%"=="true" (
    set /p INSTALL_INDEX_REPLY="Install extra language parsers: JS, Go, Rust, Java? [y/N]: "
    if /i "%INSTALL_INDEX_REPLY%"=="y" set "INSTALL_INDEX=true"
)
if "%INSTALL_INDEX%"=="true" (
    echo [INFO] Installing extra language parsers...
    pip install tree-sitter-javascript tree-sitter-go tree-sitter-rust tree-sitter-java
    if errorlevel 1 (
        echo [WARN] Some language parsers failed to install.
        echo         A C compiler may be required ^(see warning above^).
    ) else (
        echo [OK] Extra language parsers installed.
    )
)
echo(

REM --- Done ---
echo ============================================
echo  Installation Complete!
echo ============================================
echo(
echo  To use PilotCode:
echo    1. Activate venv:    .venv\Scripts\activate
echo    2. Configure LLM:    python -m pilotcode configure
echo    3. Run TUI:          .\pilotcode.cmd
echo    4. Run Web UI:       .\pilotcode.cmd --web
echo    5. Or directly:      python -m pilotcode
echo(
echo  Optional - global access without activating venv:
echo    Add .venv\Scripts to your system PATH, then use:
echo      pilotcode
echo      pilotcode --web
echo(
echo  Non-interactive install examples:
echo    install.cmd --dev
echo    install.cmd --index
echo    install.cmd --dev --index
echo ============================================
pause
