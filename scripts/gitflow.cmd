@echo off
rem Wrapper for gitflow.ps1: bypass execution policy and forward all arguments.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0gitflow.ps1" %*