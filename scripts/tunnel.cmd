@echo off
rem Wrapper for tunnel.ps1: bypass execution policy and forward all arguments.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tunnel.ps1" %*
