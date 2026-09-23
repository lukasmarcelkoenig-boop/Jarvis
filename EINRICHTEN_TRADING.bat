@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv-control\Scripts\python.exe" (
 echo Zuerst EINRICHTEN.bat ausfuehren.
 pause
 exit /b 1
)
.venv-control\Scripts\python.exe -m pip install -r requirements-trading.txt
if errorlevel 1 (
 echo MT5-Einrichtung fehlgeschlagen. Fehlermeldung oben pruefen.
 pause
 exit /b 1
)
echo Trading-Modul eingerichtet.
echo MetaTrader 5 oeffnen und in einem separaten DEMOKONTO anmelden.
echo JARVIS danach mit START_JARVIS.bat starten.
echo Anleitung: docs\control-center\TRADING.md
pause
