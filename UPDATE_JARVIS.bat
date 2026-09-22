@echo off
setlocal
cd /d "%~dp0"
echo JARVIS vorher schliessen. Lokale Aenderungen werden nicht ueberschrieben.
git branch --show-current | findstr /x "jarvis-2.0-development" >nul
if errorlevel 1 (
 echo Falscher Branch. Bitte jarvis-2.0-development verwenden.
 pause
 exit /b 1
)
git pull --ff-only origin jarvis-2.0-development
if errorlevel 1 (
 echo Update gestoppt. Lokale Aenderungen oder Verbindung pruefen.
 pause
 exit /b 1
)
call EINRICHTEN.bat
