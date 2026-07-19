@echo off
setlocal

echo EnB Multibox Manager -- Windows Setup
echo =======================================
echo.

:: Check for Python (py launcher first, then python)
where py >nul 2>&1
if %errorlevel% == 0 (
    set PYTHON=py
    goto :found_python
)
where python >nul 2>&1
if %errorlevel% == 0 (
    set PYTHON=python
    goto :found_python
)

echo Python not found.
echo.
echo Install Python 3 from https://www.python.org/
echo During install, check "Add python.exe to PATH".
echo Then re-run this script.
echo.
pause
exit /b 1

:found_python
for /f "tokens=*" %%i in ('%PYTHON% --version 2^>^&1') do set PYVER=%%i
echo Found: %PYVER%
echo.

:: Install dependencies
echo Installing dependencies...
echo.
%PYTHON% -m pip install --upgrade pywin32 psutil pynput
if %errorlevel% neq 0 (
    echo.
    echo Dependency install failed. See error above.
    pause
    exit /b 1
)

echo.
echo Dependencies installed. Launching enbmb...
echo.
echo Note: a UAC prompt is expected -- enbmb needs admin rights so the
echo       game clients don't each pop their own UAC prompt.
echo.
echo On first launch, enbmb will create a Desktop shortcut and a Start
echo Menu entry so you don't need to run this script again.
echo.

:: Launch -- main.py handles UAC elevation and shortcut creation
%PYTHON% "%~dp0main.py"

endlocal
