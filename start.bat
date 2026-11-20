@echo off
setlocal EnableExtensions DisableDelayedExpansion
title CodeFlow Launcher

set "FAILURE=Cannot open the CodeFlow folder. Use a checkout on a local Windows drive."
cd /d "%~dp0" || goto failed

set "VENV_DIR=backend\.venv"
set "VENV_PYTHON=%CD%\%VENV_DIR%\Scripts\python.exe"
if exist "%VENV_PYTHON%" (
    set "FAILURE=The existing backend\.venv must have a working Python 3.11 or newer."
    "%VENV_PYTHON%" -c "import sys; sys.exit(sys.version_info < (3, 11))" || goto failed
    goto python_ready
)

set "FAILURE=Python 3.11 or newer is required. Install it and reopen this launcher."
set "BOOTSTRAP_PYTHON=py -3"
py -3 -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if not errorlevel 1 goto python_ready
set "BOOTSTRAP_PYTHON=python"
python -c "import sys; sys.exit(sys.version_info < (3, 11))" >nul 2>&1
if errorlevel 1 goto failed

:python_ready
set "FAILURE=Node.js 22.12 or newer with npm is required. Install it and reopen this launcher."
node.exe -e "const [major, minor] = process.versions.node.split('.').map(Number); process.exit(major > 22 || (major === 22 && minor >= 12) ? 0 : 1)" >nul 2>&1
if errorlevel 1 goto failed
where npm.cmd >nul 2>&1 || goto failed

set "FAILURE=CodeFlow needs ports 8765 and 5173. Close the app using those ports and try again."
node.exe -e "const net = require('node:net'); for (const port of [8765, 5173]) { const probe = net.createServer(); probe.on('error', error => { console.error('Port ' + port + ': ' + error.message); process.exitCode = 1 }); probe.listen(port, '127.0.0.1', () => probe.close()) }"
if errorlevel 1 goto failed

if exist "%VENV_PYTHON%" goto check_backend
echo Creating %VENV_DIR%...
set "FAILURE=Could not create the Python virtual environment."
%BOOTSTRAP_PYTHON% -m venv "%VENV_DIR%" || goto failed

:check_backend
if exist "%VENV_DIR%\.codeflow-pyproject" (
    fc /b "backend\pyproject.toml" "%VENV_DIR%\.codeflow-pyproject" >nul 2>&1
    if errorlevel 1 goto install_backend
)
"%VENV_PYTHON%" -c "import app.main, uvicorn" >nul 2>&1
if not errorlevel 1 goto backend_ready

:install_backend
echo Installing Python dependencies...
set "FAILURE=Python dependency installation failed. See the pip output above."
"%VENV_PYTHON%" -m pip install -e ".\backend" || goto failed

:backend_ready
set "FAILURE=Could not save the backend dependency state."
copy /y "backend\pyproject.toml" "%VENV_DIR%\.codeflow-pyproject" >nul || goto failed

:check_frontend
if exist "frontend\node_modules\vite\bin\vite.js" (
    fc /b "frontend\package-lock.json" "frontend\node_modules\.codeflow-package-lock" >nul 2>&1
    if not errorlevel 1 goto launch
)
echo Installing frontend dependencies...
set "FAILURE=Frontend dependency installation failed. See the npm output above."
call :install_frontend
if errorlevel 1 goto failed

:launch
echo Starting CodeFlow...
set "FAILURE=Could not start CodeFlow. Check the backend and frontend windows."
start "CodeFlow Backend" "%VENV_PYTHON%" -m uvicorn app.main:app --host 127.0.0.1 --port 8765 || goto failed
start "CodeFlow Frontend" /D "%CD%\frontend" node.exe ".\node_modules\vite\bin\vite.js" --host 127.0.0.1 --port 5173 --strictPort || goto failed

set "FAILURE=CodeFlow did not become ready. Check both service windows and close them before retrying."
for /l %%I in (1,1,30) do (
    node.exe -e "fetch('http://127.0.0.1:5173/api/health', { signal: AbortSignal.timeout(1000) }).then(r => r.json()).then(h => { process.exitCode = h.status === 'ok' ? 0 : 1 }, () => { process.exitCode = 1 })" >nul 2>&1
    if not errorlevel 1 goto ready
    timeout /t 1 /nobreak >nul
)
goto failed

:ready
set "FAILURE=CodeFlow is running. Open http://127.0.0.1:5173/ in your browser."
start "" "http://127.0.0.1:5173/" || goto failed
exit /b 0

:install_frontend
pushd "frontend" || exit /b 1
call npm.cmd ci --include=dev || goto frontend_install_failed
copy /y "package-lock.json" "node_modules\.codeflow-package-lock" >nul || goto frontend_install_failed
popd
exit /b 0

:frontend_install_failed
popd
exit /b 1

:failed
echo(
echo %FAILURE%
pause
exit /b 1
