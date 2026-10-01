@echo off
setlocal
python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m playwright install chromium
if errorlevel 1 pause
 echo.
echo Setup complete. Run run.bat
pause
