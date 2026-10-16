@echo off
Title MT5 Senales
COLOR 0A
cd /d "%~dp0"

set API_PORT=8765
set WEB_PORT=5180

REM 1. MetaTrader 5 debe estar abierto y con sesion iniciada para tener precios reales
tasklist /fi "imagename eq terminal64.exe" 2>NUL | find /i "terminal64.exe" >NUL
if "%errorlevel%" NEQ "0" (
    if exist "C:\Program Files\MetaTrader 5\terminal64.exe" (
        echo Abriendo MetaTrader 5...
        start "" "C:\Program Files\MetaTrader 5\terminal64.exe"
        ping -n 9 127.0.0.1 >nul
    ) else (
        echo [ERROR] MetaTrader 5 no esta instalado en C:\Program Files\MetaTrader 5
        echo         Sin MT5 la app no muestra senales. Instalalo y vuelve a ejecutar este archivo.
        pause
        exit /b 1
    )
)

if exist "venv\Scripts\activate.bat" (call venv\Scripts\activate.bat)

REM 2. Motor (sin --reload: un reinicio en caliente cortaria el escaner en plena operacion)
curl -s -m 2 http://127.0.0.1:%API_PORT%/status 2>NUL | find "mt5-senales" >NUL
if "%errorlevel%" EQU "0" (
    echo El motor ya esta corriendo en el puerto %API_PORT%.
) else (
    netstat -ano | find "LISTENING" | find ":%API_PORT% " >NUL
    if not errorlevel 1 (
        echo [ERROR] Otro programa ocupa el puerto %API_PORT%. Cierralo y vuelve a ejecutar este archivo.
        pause
        exit /b 1
    )
    start "MT5 Senales - Motor" cmd /k "python -m uvicorn main:app --host 127.0.0.1 --port %API_PORT%"
)

REM 3. Panel
netstat -ano | find "LISTENING" | find ":%WEB_PORT% " >NUL
if errorlevel 1 (
    if exist "frontend" (
        cd frontend
        if not exist "node_modules" call npm install
        start "MT5 Senales - Panel" cmd /k "npm run dev"
        cd ..
    )
) else (
    echo El panel ya esta abierto en el puerto %WEB_PORT%.
)

REM 4. Esperar al motor antes de abrir el navegador
set /a TRIES=0
:wait_api
curl -s -m 2 http://127.0.0.1:%API_PORT%/status 2>NUL | find "mt5-senales" >NUL
if "%errorlevel%" EQU "0" goto open_panel
set /a TRIES+=1
if %TRIES% GEQ 20 (
    echo [AVISO] El motor no respondio en 40 s. Revisa la ventana "MT5 Senales - Motor".
    goto open_panel
)
ping -n 3 127.0.0.1 >nul
goto wait_api

:open_panel
start http://localhost:%WEB_PORT%
