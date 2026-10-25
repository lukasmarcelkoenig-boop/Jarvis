@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv-control\Scripts\python.exe" (
 echo Zuerst EINRICHTEN.bat starten.
 pause
 exit /b 1
)
echo JARVIS Stream Director - Erweiterungen installieren
".venv-control\Scripts\python.exe" -m pip install -r requirements-stream.txt
if errorlevel 1 (
 echo Installation fehlgeschlagen. Fehlermeldung oben pruefen.
 pause
 exit /b 1
)
".venv-control\Scripts\python.exe" -c "import obsws_python, websocket; from jarvis_control.stream_director import StreamDirector; print('Stream Director: Python-Module bereit')"
if errorlevel 1 (
 echo Modulpruefung fehlgeschlagen.
 pause
 exit /b 1
)
echo Fertig. In OBS Replay Buffer und WebSocket einschalten.
echo Danach START_JARVIS.bat ausfuehren und Stream Director oeffnen.
pause
