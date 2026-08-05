# Avvia livedub per la prova d'ascolto, con i controlli fatti **prima**.
#
#   powershell -ExecutionPolicy Bypass -File tools\prova.ps1
#   powershell -ExecutionPolicy Bypass -File tools\prova.ps1 -Traduci
#   powershell -ExecutionPolicy Bypass -File tools\prova.ps1 -Motore piper
#
# Perche' uno script e non la riga di comando scritta a mano: la riga da copiare
# e' lunga otto opzioni, e le due volte in cui e' stata copiata male non hanno
# dato errore — hanno dato una prova fatta con una configurazione diversa da
# quella che si credeva. Qui la configurazione viene **stampata** prima di
# partire, e chi legge il report sa cosa e' stato provato.
#
# I controlli sono quelli che altrimenti si scoprono a gioco avviato:
# - il venv c'e' e ha dentro il programma;
# - la scheda di cattura (`voicemeeter`) esiste, se no si sente il silenzio e si
#   incolpa il doppiaggio;
# - traducendo, Ollama e' acceso **e** ha il modello: senza, ogni battuta ricade
#   sull'originale in silenzio, che e' il difetto peggiore da diagnosticare
#   perche' il programma continua a funzionare benissimo.

[CmdletBinding()]
param(
    [switch]$Traduci,                       # sottotitoli italiani -> voce inglese
    [ValidateSet('kokoro', 'piper', 'supertonic')]
    [string]$Motore = 'kokoro',
    [string]$Da = 'it',
    [string]$A = 'en',
    [string]$Profilo = 'live',
    [string]$Loopback = 'voicemeeter',
    [switch]$Avvia,                         # non aspetta il tasto: parte da solo
    [switch]$Opaco,                         # niente colore trasparente: finestra normale
    [switch]$Catturabile,                   # l'overlay entra negli screenshot (per fotografarlo)
    [switch]$Prova                          # dice cosa farebbe e non parte
)

$ErrorActionPreference = 'Stop'
$radice = Split-Path -Parent $PSScriptRoot
$python = Join-Path $radice '.venv\Scripts\python.exe'

Write-Host ""
Write-Host "== livedub: prova d'ascolto ==" -ForegroundColor Cyan

if (-not (Test-Path $python)) {
    Write-Host "  ! manca il venv: $python" -ForegroundColor Red
    Write-Host "    si ricostruisce con:  python -m venv .venv ; .\.venv\Scripts\pip install -r requirements.txt"
    exit 1
}
Write-Host "  venv        ok"

# -- la scheda di cattura ----------------------------------------------------
# `list_devices` e' la stessa funzione che usa il programma: chiedere a lei
# invece che a Windows evita di dichiarare "c'e'" un dispositivo che poi la
# catena non trova.
$dispositivi = & $python -c @"
import sys; sys.path.insert(0, r'$radice')
from capture.audio import list_devices
loops, default = list_devices()
print('|'.join(d.name for d in loops))
print(default.name if default else '')
"@
$trovati = ($dispositivi -split "`n")[0]
if ($trovati -notmatch [regex]::Escape($Loopback)) {
    Write-Host "  ! nessuna cattura che contenga '$Loopback'" -ForegroundColor Red
    Write-Host "    ci sono: $trovati"
    Write-Host "    serve un loopback che senta il gioco (Voicemeeter, o `-Loopback <nome>`)."
    exit 1
}
Write-Host "  cattura     ok  ($Loopback)"

# -- il traduttore -----------------------------------------------------------
$modello = 'translategemma:4b'
if ($Traduci) {
    $vivo = $false
    try {
        $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 3
        $vivo = $true
    } catch { }
    if (-not $vivo) {
        $exe = Join-Path $env:LOCALAPPDATA 'Programs\Ollama\ollama.exe'
        if (-not (Test-Path $exe)) {
            Write-Host "  ! Ollama non c'e': serve per tradurre" -ForegroundColor Red
            exit 1
        }
        Write-Host "  ollama      lo accendo io..."
        Start-Process -FilePath $exe -ArgumentList 'serve' -WindowStyle Hidden
        for ($i = 0; $i -lt 20 -and -not $vivo; $i++) {
            Start-Sleep -Seconds 1
            try { $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2; $vivo = $true } catch { }
        }
    }
    if (-not $vivo) {
        Write-Host "  ! Ollama non risponde su 11434" -ForegroundColor Red
        exit 1
    }
    $nomi = (Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/tags' -TimeoutSec 5).models | ForEach-Object { $_.name }
    if ($nomi -notcontains $modello) {
        Write-Host "  ! manca il modello $modello (ci sono: $($nomi -join ', '))" -ForegroundColor Red
        Write-Host "    si scarica con:  ollama pull $modello"
        exit 1
    }
    Write-Host "  traduttore  ok  ($modello, $Da -> $A)"
}

# -- la configurazione, scritta per esteso ------------------------------------
$opzioni = @(
    '--profile', $Profilo,
    '--loopback', $Loopback,
    '--set', 'vision.ocr_backend=oneocr',
    '--set', "tts.backend=$Motore"
)
if ($Motore -eq 'kokoro') { $opzioni += @('--set', 'tts.device=cuda') }
if ($Avvia) { $opzioni += '--avvia' }
if ($Opaco) { $opzioni += @('--set', 'translate.transparent=false') }
if ($Catturabile) { $opzioni += '--overlay-catturabile' }
if ($Traduci) {
    $opzioni += @(
        '--set', 'translate.enabled=true',
        '--set', 'translate.backend=ollama',
        '--set', "translate.source=$Da",
        '--set', "translate.target=$A"
    )
}

Write-Host ""
Write-Host "  motore      $Motore"
Write-Host "  profilo     $Profilo"
if ($Opaco) { Write-Host "  overlay     finestra opaca (niente colore trasparente)" }
if ($Catturabile) { Write-Host "  overlay     catturabile: entra negli screenshot, e l'OCR lo legge" -ForegroundColor Yellow }
if ($Traduci) {
    Write-Host "  traduzione  $Da -> $A, la riga originale viene cancellata"
} else {
    Write-Host "  traduzione  spenta (i sottotitoli sono gia' italiani)"
}
Write-Host ""
if ($Avvia) {
    Write-Host "  Parte da sola con l'area del profilo. Se non e' quella giusta:"
    Write-Host "  'Ferma' -> 'Seleziona area' -> 'Avvia'."
} else {
    Write-Host "  Nella finestra:  'Scegli finestra' -> 'Seleziona area' -> 'Avvia'."
}
Write-Host "  Alla fine 'Ferma': la sessione finisce in runs\<data-ora>." -ForegroundColor Yellow
Write-Host ""

if ($Prova) {
    Write-Host "prova: non parte niente." -ForegroundColor Yellow
    Write-Host "  $python -m tools.ui $($opzioni -join ' ')"
    exit 0
}

Push-Location $radice
try { & $python -m tools.ui @opzioni } finally { Pop-Location }
