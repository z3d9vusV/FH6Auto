@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

set APP_NAME=FH6Auto
set MAIN_FILE=main.py

echo.
echo ==============================
echo Starting to package %APP_NAME%
echo ==============================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [Error] Python not found. Please configure the environment variables first
    pause
    exit /b 1
)

echo [1/3] Cleaning up old files...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
if exist "%APP_NAME%.spec" del /f /q "%APP_NAME%.spec"

echo [2/3] Running PyInstaller...
python -m PyInstaller ^
    -n "%APP_NAME%" ^
    -F ^
    -w ^
    --uac-admin ^
    "%MAIN_FILE%" ^
    --icon=assets/icon.ico ^
    --add-data "images;images" ^
    --add-data "assets;assets"

if errorlevel 1 (
    echo.
    echo [Error] Packaging failed!
    pause
    exit /b 1
)

echo.
echo [3/3] Packaging complete!
echo Output directory: dist\%APP_NAME%.exe
echo.
pause
