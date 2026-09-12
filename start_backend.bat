@echo off
echo Starting Backend...
echo.

REM Kill existing python processes on port 8000
netstat -ano | findstr ":8000" | findstr "LISTENING" > nul
if %errorlevel% == 0 (
    echo Stopping old backend...
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000 ^| findstr LISTENING"') do (
        taskkill /F /PID %%a > nul 2>&1
    )
    timeout /t 2 > nul
)

echo Starting backend in backend\ directory...
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

pause