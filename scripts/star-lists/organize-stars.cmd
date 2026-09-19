@echo off
setlocal
cd /d "%~dp0..\.."
where python >nul 2>&1 && set PY=python
if not defined PY where py >nul 2>&1 && set PY=py -3
if not defined PY (
  echo Python not found. Install Python 3 from https://python.org and try again.
  exit /b 1
)
%PY% scripts\star-lists\apply-lists.py %*
