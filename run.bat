@echo off
setlocal
set "ROOT=%~dp0"
set "VENV_DIR=%ROOT%.venv"
set "PY=%VENV_DIR%\Scripts\python.exe"
set "PYW=%VENV_DIR%\Scripts\pythonw.exe"
set "APP=%ROOT%Setup Manager\main.py"
set "LIB_APP=%ROOT%Tools and jaws Library\main.py"
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

call :kill_old_instances

call :ensure_venv
if not "%ERRORLEVEL%"=="0" (
	pause
	exit /b 1
)

REM Use pythonw for silent launch, or python if pythonw not available
if exist "%PYW%" (
	REM pythonw.exe is designed to run without console window - launch directly
	"%PYW%" "%APP%" %*
) else (
	REM Fallback: launch python with minimized window
	start "" /min "%PY%" "%APP%" %*
)
set "EC=%ERRORLEVEL%"
exit /b %EC%
set "EC=%ERRORLEVEL%"
if not "%EC%"=="0" pause
exit /b %EC%

:ensure_venv
set "MARKER=%VENV_DIR%\.library_ready"
set "LEGACY_MARKER=%VENV_DIR%\.ntx_ready"

if exist "%MARKER%" if exist "%PY%" goto :venv_ready
if exist "%LEGACY_MARKER%" if exist "%PY%" (
	echo Found legacy venv marker. Migrating to .library_ready...
	move /y "%LEGACY_MARKER%" "%MARKER%" >nul 2>nul
	goto :venv_ready
)

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

echo library_ready > "%MARKER%"

:venv_ready
exit /b 0

:kill_old_instances
where powershell >nul 2>&1
if errorlevel 1 exit /b 0

powershell -NoProfile -ExecutionPolicy Bypass -Command "$targets = @('%APP%', '%LIB_APP%'); $procs = @(Get-CimInstance Win32_Process | Where-Object { $cmd = $_.CommandLine; if (-not $cmd) { return $false }; if ($_.Name -notmatch '^pythonw?(\.exe)?$') { return $false }; foreach ($t in $targets) { if ($t -and $cmd -like ('*' + $t + '*')) { return $true } }; return $false }); if ($procs.Count -gt 0) { foreach ($p in $procs) { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue }; Write-Host ('Closed old instance(s): ' + $procs.Count) }"
exit /b 0
