@echo off
cd /d "%~dp0"
echo ============================================
echo  LogixTrek Direct Shipper Outreach
echo ============================================
echo.
where python >nul 2>nul
if errorlevel 1 (
  echo.
  echo Python was not found on this PC.
  echo 1. Go to https://www.python.org/downloads/
  echo 2. Install Python 3.12
  echo 3. CHECK THE BOX: Add python.exe to PATH
  echo 4. Close this window and double-click START_APP.bat again
  echo.
  pause
  exit /b 1
)
python --version | findstr /i "Python 3." >nul
if errorlevel 1 (
  echo Python exists but may be the Microsoft Store stub. Install from python.org with PATH enabled.
  pause
  exit /b 1
)
echo Installing / updating packages...
python -m pip install -r requirements.txt
echo.
echo Starting the app in your browser...
echo Keep this window open while you use the tool.
echo.
python -m streamlit run app.py
pause
