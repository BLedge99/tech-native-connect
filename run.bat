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
if "%CMD%"=="build" goto build
if "%CMD%"=="down" goto down
if "%CMD%"=="logs" goto logs
if "%CMD%"=="clean" goto clean
if "%CMD%"=="panel" goto panel
if "%CMD%"=="devcheck" goto devcheck
goto help

:dev
%DOCKER_CMD% compose up --build
goto end

:panel
start http://localhost:5173/dev
goto end

REM Dev-tooling contract tests: Adminer, Mailpit, dev panel, videos.
REM These must run inside the compose network, so they are executed in the
REM frontend container and target service hostnames (adminer:8080) rather than
REM published localhost ports.
:devcheck
%DOCKER_CMD% compose exec -T frontend npx playwright install chromium
%DOCKER_CMD% compose exec -T frontend npx playwright test -c playwright.devtools.config.ts
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
echo Usage: run.bat [dev^|build^|down^|logs^|clean^|panel^|devcheck]
echo   dev      - Build and start all services (default)
echo   build    - Build images only
echo   down     - Stop services
echo   logs     - Follow logs
echo   clean    - Stop and delete all data
echo   panel    - Open the dev panel in your browser
echo   devcheck - Test Adminer, Mailpit and the dev panel end to end

:end
endlocal
