@echo off
rem Doppio clic per aprire livedub, senza riga di comando.
rem E' la domanda 1 di DOMANDE_PRODUZIONE.md: chi scarica il repo non deve
rem dover sapere cos'e' un venv per vedere la finestra.
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Manca l'ambiente. Lancio l'installazione...
    powershell -ExecutionPolicy Bypass -File "installa.ps1"
)
if not exist ".venv\Scripts\python.exe" (
    echo Installazione non riuscita: apri installa.ps1 e guarda cosa manca.
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m tools.ui_qt %*
