@echo off
Title MT5 Quant Pro Terminal
COLOR 0A
cd /d "%~dp0"

REM 1. MetaTrader 5 debe estar abierto y con sesion iniciada para tener precios reales
tasklist /fi "imagename eq terminal64.exe" 2>NUL | find /i "terminal64.exe" >NUL
if "%errorlevel%" NEQ "0" (
    if exist "C:\Program Files\MetaTrader 5\terminal64.exe" (
        echo Abriendo MetaTrader 5...
        start "" "C:\Program Files\MetaTrader 5\terminal64.exe"
        timeout /t 8 >nul
    ) else (
        echo [ERROR] MetaTrader 5 no esta instalado en C:\Program Files\MetaTrader 5
        echo         Sin MT5 la app no muestra senales. Instalalo y vuelve a ejecutar este archivo.
        pause
        exit /b 1
    )
)

if exist "venv\Scripts\activate.bat" (call venv\Scripts\activate.bat)

REM 2. Backend (sin --reload: un reinicio en caliente cortaria el escaner en plena operacion)
start "MT5 Backend API" cmd /k "python -m uvicorn main:app --host 127.0.0.1 --port 8000"

REM 3. Frontend
if exist "frontend" (
    cd frontend
    if not exist "node_modules" call npm install
    start "MT5 Frontend" cmd /k "npm run dev"
    cd ..
)

timeout /t 4 >nul
start http://localhost:5173
