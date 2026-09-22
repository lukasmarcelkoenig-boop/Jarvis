@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv-control\Scripts\python.exe" (
 echo Zuerst EINRICHTEN.bat starten.
 pause
 exit /b 1
)
echo Browser-Adresse: http://127.0.0.1:8765
echo Anmeldung: .jarvis-data\LOGIN_CODE.txt
.venv-control\Scripts\python.exe -m jarvis_control
pause
