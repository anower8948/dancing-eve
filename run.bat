@echo off
rem Project EVE launcher for Windows 10/11 - double-click in Explorer.
rem First run: creates .venv, installs pinned dependencies with a progress display, launches EVE.
rem Later runs: reuse the environment and start EVE immediately.
setlocal EnableExtensions
cd /d "%~dp0"
set "PYEXE="

rem Any Python >= 3.8 can run the bootstrap; it then selects 3.11-3.13 for the virtual environment.
where py >nul 2>nul
if %ERRORLEVEL%==0 (
  py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
  if not errorlevel 1 set "PYEXE=py -3"
)
if not defined PYEXE (
  rem "python" may be the Microsoft Store alias, which fails this check and is skipped.
  python -c "import sys; sys.exit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
  if not errorlevel 1 set "PYEXE=python"
)
if not defined PYEXE goto :nopython

%PYEXE% "%~dp0setup\bootstrap.py" %*
set "CODE=%ERRORLEVEL%"
if not "%CODE%"=="0" (
  echo.
  echo Project EVE stopped with exit code %CODE%.
  pause
)
exit /b %CODE%

:nopython
echo Project EVE needs Python 3.11, 3.12 or 3.13, and none was found.
where winget >nul 2>nul
if %ERRORLEVEL%==0 (
  echo EVE can install Python 3.12 for your user account with:
  echo     winget install --exact --id Python.Python.3.12 --scope user
  choice /C YN /M "Install Python 3.12 now"
  if not errorlevel 2 (
    winget install --exact --id Python.Python.3.12 --scope user
    echo.
    echo Python was installed. Close this window and double-click run.bat again.
    pause
    exit /b 2
  )
)
echo Please install Python 3.12 from https://www.python.org/downloads/windows/
echo (tick "Add python.exe to PATH"), then double-click run.bat again.
pause
exit /b 2
