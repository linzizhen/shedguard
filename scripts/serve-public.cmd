@echo off
rem Wrapper for serve-public.ps1: bypass execution policy and forward all arguments.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0serve-public.ps1" %*
