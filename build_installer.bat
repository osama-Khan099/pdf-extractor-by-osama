@echo off
setlocal
REM Builds the app, then packs it into installer\PDF-Extractor-by-Osama-Setup-1.2.0.exe
REM That one file can be copied to any Windows 10/11 PC and installed. No Python needed there.
cd /d "%~dp0"

call "%~dp0build_exe.bat" nopause
if errorlevel 1 goto :fail

set "ISCC="
for %%P in ("%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe" "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe") do (
  if exist %%P set "ISCC=%%~P"
)
if not defined ISCC (
  where iscc >nul 2>nul && set "ISCC=iscc"
)
if not defined ISCC (
  echo.
  echo Inno Setup 6 is needed to make the installer and was not found.
  where winget >nul 2>nul
  if errorlevel 1 (
    echo Install it from https://jrsoftware.org/isdl.php and run this again.
    goto :fail
  )
  choice /m "Install Inno Setup now with winget"
  if errorlevel 2 goto :fail
  winget install -e --id JRSoftware.InnoSetup --scope user --accept-package-agreements --accept-source-agreements
  if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
  if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
  if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
  if not defined ISCC (
    echo ERROR: Inno Setup still not found. Install it from https://jrsoftware.org/isdl.php
    goto :fail
  )
)

echo.
echo Building installer with "%ISCC%"...
"%ISCC%" installer.iss
if errorlevel 1 (
  echo ERROR: making the installer failed. See the messages above.
  goto :fail
)

echo.
echo Done. Share this file: installer\PDF-Extractor-by-Osama-Setup-1.2.0.exe
pause
exit /b 0

:fail
echo.
pause
exit /b 1
