@echo off
setlocal
cd /d "%~dp0"

docker compose version >nul 2>&1
if errorlevel 1 (
    echo Docker Desktop must be installed and running to start Cohort Connect.
    exit /b 1
)

docker compose up -d --build
if errorlevel 1 exit /b 1

echo Cohort Connect is running:
echo   Frontend: http://localhost:5173
echo   API:      http://localhost:8000
echo   Mailpit:  http://localhost:8025
