@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0agent-cli.ps1" %*
exit /b %ERRORLEVEL%
