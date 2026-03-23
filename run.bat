@echo off
setlocal
set "ROOT=%~dp0"
set "VENV_DIR=%ROOT%.venv"
set "PY=%VENV_DIR%\Scripts\python.exe"
set "APP=%ROOT%Setup Manager\main.py"
set "REQ=%ROOT%Setup Manager\requirements.txt"

if not exist "%APP%" (
	echo Application entry point not found:
	echo %APP%
	pause
	exit /b 1
)

if not exist "%REQ%" (
	echo Requirements file not found:
	echo %REQ%
	pause
	exit /b 1
)

call :ensure_venv
if not "%ERRORLEVEL%"=="0" (
	pause
	exit /b 1
)

"%PY%" "%APP%" %*
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" pause
exit /b %EC%

:ensure_venv
set "MARKER=%VENV_DIR%\.ntx_ready"

if exist "%MARKER%" if exist "%PY%" goto :venv_ready

if exist "%VENV_DIR%" (
	echo Virtual environment incomplete or moved. Recreating...
	rmdir /s /q "%VENV_DIR%" 2>nul
	REM If python.exe survived (files locked by running app), use the existing venv
	if exist "%PY%" (
		echo Note: some files are in use. Using existing installation.
		goto :write_marker
	)
)

set "VENV_CREATED=0"
where python >nul 2>&1
if not errorlevel 1 (
	python -m venv "%VENV_DIR%"
	if not errorlevel 1 set "VENV_CREATED=1"
)

if not "%VENV_CREATED%"=="1" (
	where py >nul 2>&1
	if not errorlevel 1 (
		py -3 -m venv "%VENV_DIR%"
		if not errorlevel 1 set "VENV_CREATED=1"
	)
)

if not "%VENV_CREATED%"=="1" (
	echo Python was not found. Install Python 3.10+ and try again.
	exit /b 1
)

if not exist "%PY%" (
	echo Failed to create virtual environment.
	exit /b 1
)

"%PY%" -m pip install --upgrade pip
if not errorlevel 1 goto :pip_ok
exit /b 1
:pip_ok

"%PY%" -m pip install -r "%REQ%"
if not errorlevel 1 goto :write_marker
exit /b 1
:write_marker

echo ntx_ready > "%MARKER%"

:venv_ready
exit /b 0
