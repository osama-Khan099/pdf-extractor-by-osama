@echo off
setlocal
REM Builds a standalone PDFExtractor.exe in the dist folder (Windows).
cd /d "%~dp0"

if not exist "app.py" (
  echo ERROR: app.py not found next to this script.
  echo Extract the whole zip to a folder first, then run build_exe.bat from there.
  goto :fail
)

set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY (
  python -c "import sys" >nul 2>nul && set "PY=python"
)
if not defined PY (
  echo ERROR: Python was not found.
  echo Install Python 3.10 or newer from https://www.python.org/downloads/
  echo and tick "Add python.exe to PATH" during setup, then run this again.
  goto :fail
)

echo Using: %PY%
%PY% --version
echo.
echo Installing requirements...
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt pyinstaller
if errorlevel 1 (
  echo ERROR: installing requirements failed. See the messages above.
  goto :fail
)

echo.
echo Building PDFExtractor.exe...
%PY% -m PyInstaller --noconfirm --windowed --name PDFExtractor --collect-all rapidocr_onnxruntime --collect-data pymupdf app.py
if errorlevel 1 (
  echo ERROR: the build failed. See the messages above.
  goto :fail
)

echo.
echo Done. Your app is in dist\PDFExtractor\PDFExtractor.exe
if /i not "%~1"=="nopause" pause
exit /b 0

:fail
echo.
if /i not "%~1"=="nopause" pause
exit /b 1
