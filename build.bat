@echo off
setlocal

set "ROOT=%~dp0"
set "BUILD_VENV=%ROOT%.buildvenv"
set "PY=%BUILD_VENV%\Scripts\python.exe"
set "APP_DIR=%ROOT%Setup Manager"
set "REQ=%APP_DIR%\requirements-build.txt"
set "SPEC=%APP_DIR%\ntx_tool_library.spec"

echo [1/4] Checking inputs...
if not exist "%REQ%" (
    echo Build requirements file not found:
    echo %REQ%
    exit /b 1
)
if not exist "%SPEC%" (
    echo PyInstaller spec file not found:
    echo %SPEC%
    exit /b 1
)

echo [2/4] Preparing local build environment...
if not exist "%PY%" (
    where python >nul 2>&1
    if not errorlevel 1 (
        python -m venv "%BUILD_VENV%"
    ) else (
        where py >nul 2>&1
        if not errorlevel 1 (
            py -3 -m venv "%BUILD_VENV%"
        ) else (
            echo Python was not found. Install Python 3.10+ and try again.
            exit /b 1
        )
    )
)

if not exist "%PY%" (
    echo Failed to create build environment.
    exit /b 1
)

echo [3/4] Installing build dependencies...
"%PY%" -m pip install --upgrade pip
if not errorlevel 1 goto :pip_ok
exit /b 1
:pip_ok

"%PY%" -m pip install -r "%REQ%"
if not errorlevel 1 goto :pip2_ok
exit /b 1
:pip2_ok

echo [4/4] Building portable app...
pushd "%APP_DIR%"
"%PY%" -m PyInstaller --noconfirm --clean "%SPEC%"
set "EC=%ERRORLEVEL%"
popd
if not "%EC%"=="0" exit /b %EC%

echo.
echo Build completed successfully.
echo Share this folder:
echo %APP_DIR%\dist\NTX Setup Manager
echo.
echo Launch on target machine with:
echo NTX Setup Manager.exe

exit /b 0
