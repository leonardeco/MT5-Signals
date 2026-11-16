@echo off
REM Motor en un VPS Windows: abre MetaTrader 5, arranca el motor y lo relanza si se cae.
REM Pensado para la tarea programada "al iniciar sesion" (ver docs/vps.md). No abre el panel ni el navegador.
Title MT5 Senales - Motor VPS
COLOR 0A
cd /d "%~dp0.."

set API_PORT=8765
if not defined MT5_PATH set "MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe"

REM 1. Sin clave no se arranca: en un VPS el motor no debe quedar sin proteccion
if not exist "motor.env" (
    echo [ERROR] Falta motor.env con MT5_TOKEN_OPERAR. Copia motor.env.example y rellena la clave.
    pause
    exit /b 1
)
findstr /r /c:"^MT5_TOKEN_OPERAR=..*" /c:"^MT5_TOKEN_LECTURA=..*" motor.env >NUL
if errorlevel 1 (
    echo [ERROR] motor.env no tiene ninguna clave. Genera una con:
    echo         python -c "import secrets; print(secrets.token_urlsafe(32))"
    pause
    exit /b 1
)

if exist "venv\Scripts\activate.bat" (call venv\Scripts\activate.bat)

:loop
REM 2. MetaTrader 5 abierto y con sesion iniciada (guarda la contrasena al conectarte la primera vez)
tasklist /fi "imagename eq terminal64.exe" 2>NUL | find /i "terminal64.exe" >NUL
if errorlevel 1 (
    if not exist "%MT5_PATH%" (
        echo [ERROR] MetaTrader 5 no esta en %MT5_PATH%
        pause
        exit /b 1
    )
    echo %date% %time% Abriendo MetaTrader 5...
    start "" "%MT5_PATH%"
    ping -n 20 127.0.0.1 >nul
)

REM 3. Motor solo en 127.0.0.1: desde fuera se llega por Tailscale (tailscale serve), nunca abriendo el puerto
echo %date% %time% Arrancando el motor en 127.0.0.1:%API_PORT%
python -m uvicorn main:app --host 127.0.0.1 --port %API_PORT% >> motor.log 2>&1
echo %date% %time% El motor se detuvo (codigo %errorlevel%). Reinicio en 15 s... >> motor.log
echo %date% %time% El motor se detuvo. Reinicio en 15 s...
ping -n 16 127.0.0.1 >nul
goto loop
