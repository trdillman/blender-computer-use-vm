@echo off
:: ============================================================================
:: Blender Computer-Use VM & MCP Server - One-Click Launcher
:: Automatically elevates to Administrator and executes master setup.
:: ============================================================================
title Blender Computer-Use VM Setup

:: Check for administrative rights
net session >nul 2>&1
if %errorLevel% == 0 (
    goto :run_installer
) else (
    echo Requesting administrative privileges...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process powershell -Verb RunAs -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \""%~dp0install.ps1\""'"
    exit /b
)

:run_installer
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
pause
