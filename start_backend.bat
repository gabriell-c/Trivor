@echo off
setlocal
echo Starting Backend...
echo.

REM Mata apenas o(s) PID especifico(s) que esta(o) LISTENING na porta 8000.
REM Nunca mata todos os processos do sistema. Se nao ha processo na porta,
REM o for nao itera e nada acontece (sem erro).
set "pid_found="
for /f "tokens=5" %%a in ('netstat -ano ^| findstr "LISTENING" ^| findstr ":8000"') do (
    set "pid_found=1"
    echo Stopping old backend - PID %%a -
    taskkill /F /PID %%a > nul 2>&1
)
if defined pid_found (
    timeout /t 2 > nul
)

echo Starting backend in backend\ directory...
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause
endlocal
