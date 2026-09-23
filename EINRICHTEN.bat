@echo off
setlocal
cd /d "%~dp0"
echo JARVIS 2.0 - Einrichtung
py -3.12 --version >nul 2>&1
if errorlevel 1 (
 echo Bitte Python 3.12 von https://www.python.org/downloads/windows/ installieren.
 echo Dabei Python Launcher und Add Python to PATH aktivieren.
 pause
 exit /b 1
)
py -3.12 -m venv .venv-control
if errorlevel 1 goto failed
.venv-control\Scripts\python.exe -m pip install -r requirements-trading.txt
if errorlevel 1 goto failed
.venv-control\Scripts\python.exe -m playwright install chromium
if errorlevel 1 (
 echo Browser-Download fehlgeschlagen. Andere Module sind eingerichtet.
 echo Erneut EINRICHTEN.bat starten, um den Browser nachzuinstallieren.
)
.venv-control\Scripts\python.exe -c "from jarvis_control.state import State; from pathlib import Path; s=State('.jarvis-data'); (s.root/'workspace').mkdir(exist_ok=True); print('Anmeldecode: '+str(s.token_file))"
echo Einrichtung abgeschlossen. Jetzt START_JARVIS.bat starten.
echo Ollama und Handy-Zugang: docs\control-center\EINRICHTUNG.md
pause
exit /b 0
:failed
echo Einrichtung fehlgeschlagen. Die Fehlermeldung oben pruefen.
pause
exit /b 1
