@echo off
setlocal EnableDelayedExpansion

REM ── Detect docker ──────────────────────────────────────────────────────────
REM Works with: Docker Desktop (Windows), Docker Desktop (WSL2 backend),
REM and docker installed inside WSL.
set "DOCKER_CMD=docker"

REM Test if docker actually works (not just if it exists on PATH)
docker info >nul 2>&1
if errorlevel 1 (
    REM docker command failed — try WSL
    wsl docker info >nul 2>&1
    if errorlevel 1 (
        echo ERROR: docker is not available.
        echo Make sure Docker Desktop is running, or docker is installed in WSL.
        echo Install Docker Desktop: https://www.docker.com/products/docker-desktop/
        exit /b 1
    )
    set "DOCKER_CMD=wsl docker"
    echo [run.bat] docker not working on Windows — using WSL.
)

REM ── Parse command ──────────────────────────────────────────────────────────
set "CMD=%1"
if "%CMD%"=="" set "CMD=dev"

if "%CMD%"=="dev" goto dev
if "%CMD%"=="tunnel" goto tunnel
if "%CMD%"=="cloudflare" goto tunnel
if "%CMD%"=="url" goto url
if "%CMD%"=="build" goto build
if "%CMD%"=="down" goto down
if "%CMD%"=="logs" goto logs
if "%CMD%"=="clean" goto clean
if "%CMD%"=="panel" goto panel
goto help

:dev
%DOCKER_CMD% compose up --build
goto end

:tunnel
%DOCKER_CMD% compose up -d --build
echo.
echo [run.bat] Waiting for Cloudflare Tunnel to establish...
powershell -NoProfile -Command "$found = $false; for ($i=0; $i -lt 30; $i++) { $logs = (%DOCKER_CMD% compose logs tunnel 2>&1 | Out-String); if ($logs -match 'https://[a-zA-Z0-9-]+\.trycloudflare\.com') { Write-Host ''; Write-Host '===================================================' -ForegroundColor Green; Write-Host '  Cloudflare Tunnel is LIVE! Open to web traffic:  ' -ForegroundColor Green; Write-Host ('  ' + $matches[0]) -ForegroundColor Cyan; Write-Host '===================================================' -ForegroundColor Green; Write-Host ''; $found = $true; break }; Start-Sleep -Seconds 1 }; if (-not $found) { Write-Host '[run.bat] Tunnel container started. Check URL with: %DOCKER_CMD% compose logs tunnel' -ForegroundColor Yellow }"
goto end

:url
powershell -NoProfile -Command "$logs = (%DOCKER_CMD% compose logs tunnel 2>&1 | Out-String); if ($logs -match 'https://[a-zA-Z0-9-]+\.trycloudflare\.com') { Write-Host $matches[0] -ForegroundColor Cyan } else { Write-Host 'No active tunnel URL found. Run: %DOCKER_CMD% compose logs tunnel' -ForegroundColor Yellow }"
goto end

:panel
start http://localhost:5173/dev
goto end

:build
%DOCKER_CMD% compose build
goto end

:down
%DOCKER_CMD% compose down
goto end

:logs
%DOCKER_CMD% compose logs -f
goto end

:clean
%DOCKER_CMD% compose down -v
goto end

:help
echo Usage: run.bat [dev^|tunnel^|url^|build^|down^|logs^|clean^|panel]
echo   dev    - Build and start all services (default)
echo   tunnel - Start stack in background and display live Cloudflare URL
echo   url    - Display the active Cloudflare Tunnel URL
echo   build  - Build images only
echo   down   - Stop services
echo   logs   - Follow logs
echo   clean  - Stop and delete all data
echo   panel  - Open the dev panel in your browser

:end
endlocal
