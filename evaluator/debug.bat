@echo off
chcp 65001 >nul 2>&1
title BioDize — Rule Debugger
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel% neq 0 (
    echo Python nicht gefunden. Bitte Python 3.10+ installieren.
    pause & exit /b 1
)

py debugger.py %*
if %errorlevel% neq 0 pause
