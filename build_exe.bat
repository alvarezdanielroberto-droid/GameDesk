@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================
echo   Building GameDesk.exe
echo ============================================
where py >nul 2>nul
if errorlevel 1 (
  echo Python was not found. Install it from https://www.python.org/downloads/
  echo ^(check "Add Python to PATH" and keep tcl/tk enabled^)
  pause
  exit /b 1
)
rem icoextract = extracts each .exe's icon for the small image
py -m pip install --upgrade pillow icoextract pyinstaller
py -m PyInstaller --clean --onefile --noconsole --name GameDesk --hidden-import icoextract --hidden-import pefile gamedesk.py
if exist dist\GameDesk.exe (
  copy /y dist\GameDesk.exe GameDesk.exe >nul
  echo.
  echo Done: GameDesk.exe was created in this folder.
) else (
  echo Something went wrong while building the exe.
)
pause
