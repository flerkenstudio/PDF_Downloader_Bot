@echo off
setlocal
if not exist .venv\Scripts\python.exe (
  echo Please run setup.bat first.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m src.main --excel input.xlsx --all-years --headed
pause
