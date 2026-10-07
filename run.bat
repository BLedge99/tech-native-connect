@echo off
setlocal EnableDelayedExpansion

REM ── Detect docker ──────────────────────────────────────────────────────────
REM Works with: Docker Desktop (Windows), Docker Desktop (WSL2 backend),
REM and docker installed inside WSL.
set "DOCKER_CMD=docker"

where docker >nul 2>&1
if errorlevel 1 (
    REM docker not on Windows PATH — try WSL
    where wsl >nul 2>&1
    if errorlevel 1 (
        echo ERROR: docker is not installed and WSL is not available.
        echo Install Docker Desktop: https://www.docker.com/products/docker-desktop/
        exit /b 1
    )
    set "DOCKER_CMD=wsl docker"
    echo [run.bat] docker not found on Windows PATH — using WSL.
)

REM ── Parse command ──────────────────────────────────────────────────────────
set "CMD=%1"
if "%CMD%"=="" set "CMD=dev"

if "%CMD%"=="dev" goto dev
if "%CMD%"=="build" goto build
if "%CMD%"=="down" goto down
if "%CMD%"=="logs" goto logs
if "%CMD%"=="clean" goto clean
goto help

:dev
%DOCKER_CMD% compose up --build
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
echo Usage: run.bat [dev^|build^|down^|logs^|clean]
echo   dev    - Build and start all services (default)
echo   build  - Build images only
echo   down   - Stop services
echo   logs   - Follow logs
echo   clean  - Stop and delete all data

:end
endlocal
