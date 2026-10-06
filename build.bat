@echo off
rem Сборка Windows-exe «Учёт личных финансов».
rem Нужен установленный Python 3.x для Windows (python.org) с tkinter.
rem Запуск:  build.bat
setlocal

where python >nul 2>nul || (
    echo Python не найден в PATH. Установите https://www.python.org/downloads/windows/
    exit /b 1
)

python -m pip install --upgrade pyinstaller
python -m PyInstaller --noconfirm --clean finance.spec

if not exist dist\PersonalFinance.exe (
    echo.
    echo Ошибка сборки.
    exit /b 1
)

echo.
echo Готово: dist\PersonalFinance.exe
echo База данных finance.db создаётся рядом с exe при первом запуске.