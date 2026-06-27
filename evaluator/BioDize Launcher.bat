@echo off
chcp 65001 >nul 2>&1
title BioDize Evaluator
cd /d "%~dp0"
where py >nul 2>&1 || (echo Python nicht gefunden. & pause & exit /b 1)
py -B launcher.pyw %*
if %errorlevel% neq 0 pause
