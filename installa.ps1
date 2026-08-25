<#
.SYNOPSIS
    Installa livedub da zero su una macchina pulita.

.DESCRIPTION
    Un colpo solo: controlla Python, crea il venv, installa le dipendenze, copia
    OneOCR da Windows, scarica i modelli e **verifica di aver ottenuto quello che
    ha chiesto** invece di dire "fatto".

    Quest'ultima parte e' la ragione per cui questo file esiste invece di tre
    righe di istruzioni. Questo progetto ha gia' pagato due volte per un ripiego
    silenzioso: ORT che non trova le DLL CUDA e torna sulla CPU senza dirlo (708
    ms stavano per essere riportati come "il numero della GPU"), e OneOCR che non
    parte e lascia un doppiaggio che legge peggio senza spiegazione. Chi installa
    deve sapere **cosa ha ottenuto**, non cosa e' stato tentato.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File installa.ps1
    powershell -ExecutionPolicy Bypass -File installa.ps1 -SenzaGpu
#>
[CmdletBinding()]
param(
    # Senza GPU NVIDIA: si installa `onnxruntime` normale e si mette Piper come
    # motore. Non e' un ripiego morbido — Kokoro su CPU costa 725 ms a battuta
    # contro 207, cioe' non e' vivibile — quindi va **dichiarato**.
    [switch]$SenzaGpu,
    # Salta il download dei modelli: utile per rifare solo l'ambiente.
    [switch]$SenzaModelli
)

$ErrorActionPreference = "Stop"
$radice = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $radice

$esiti = [ordered]@{}
function Esito($nome, $ok, $nota) {
    $esiti[$nome] = @{ ok = $ok; nota = $nota }
    $segno = if ($ok) { "  ok  " } else { " MANCA" }
    $colore = if ($ok) { "Green" } else { "Yellow" }
    Write-Host ("{0}  {1,-22} {2}" -f $segno, $nome, $nota) -ForegroundColor $colore
}

Write-Host "`n=== livedub, installazione ===`n" -ForegroundColor Cyan

# -- 1. Python ---------------------------------------------------------------
# **La versione conta.** Le ruote di onnxruntime-gpu e PyAudioWPatch usate qui
# sono per 3.11; su 3.12+ pip ricompila o non trova niente, e il guasto arriva
# molto piu' tardi sotto forma di import che fallisce.
$py = $null
foreach ($c in @("py -3.11", "python")) {
    try {
        $v = & ([scriptblock]::Create("$c --version")) 2>&1
        if ($v -match "3\.11") { $py = $c; break }
    } catch { }
}
if (-not $py) {
    Esito "Python 3.11" $false "non trovato: installa Python 3.11 (https://www.python.org/downloads/)"
    Write-Host "`nSenza Python 3.11 non si va avanti.`n" -ForegroundColor Red
    exit 1
}
Esito "Python 3.11" $true (& ([scriptblock]::Create("$py --version")) 2>&1)

# -- 2. venv -----------------------------------------------------------------
$pyexe = Join-Path $radice ".venv\Scripts\python.exe"
if (-not (Test-Path $pyexe)) {
    Write-Host "  ... creo .venv" -ForegroundColor DarkGray
    & ([scriptblock]::Create("$py -m venv .venv"))
}
if (-not (Test-Path $pyexe)) {
    Esito "venv" $false "non creato"
    exit 1
}
Esito "venv" $true ".venv"

# -- 3. dipendenze -----------------------------------------------------------
Write-Host "  ... installo le dipendenze (qualche minuto)" -ForegroundColor DarkGray
& $pyexe -m pip install --upgrade pip --quiet
if ($SenzaGpu) {
    # I due pacchetti **non convivono**: installare `onnxruntime` accanto a
    # `onnxruntime-gpu` rompe la risoluzione delle DLL. Quindi si sceglie, non si
    # somma.
    $req = Get-Content requirements.txt | Where-Object { $_ -notmatch "^onnxruntime-gpu" }
    $tmp = Join-Path $env:TEMP "livedub-req-cpu.txt"
    ($req + "onnxruntime==1.28.0") | Set-Content -Path $tmp -Encoding utf8
    & $pyexe -m pip install -r $tmp --quiet
} else {
    & $pyexe -m pip install -r requirements.txt --quiet
}
$ok = $LASTEXITCODE -eq 0
Esito "dipendenze" $ok $(if ($ok) { "da requirements.txt" } else { "pip ha fallito" })

# -- 4. OneOCR ---------------------------------------------------------------
# Non ridistribuibile: si copia dalla macchina, dove l'utente ce l'ha gia' con la
# sua licenza Windows. Si veda docs/LICENZE.md.
if (Test-Path "models\oneocr\oneocr.onemodel") {
    Esito "OneOCR" $true "gia' presente"
} else {
    & $pyexe -m tools.fetch_oneocr 2>&1 | Out-Null
    $ok = Test-Path "models\oneocr\oneocr.onemodel"
    Esito "OneOCR" $ok $(if ($ok) { "copiato da Windows" } else { "non copiato: serve lo Strumento di cattura di Windows 11. Si usera' ppocr, che legge peggio sul testo bordato dei giochi" })
}

# -- 5. la GPU, verificata invece che sperata --------------------------------
# **La funzione si chiama `preload`, non `preload_dlls`.** Con il nome sbagliato
# l'import sollevava, il `try` lo mangiava, e questo installatore diceva «nessun
# provider CUDA» su **qualunque** macchina — comprese quelle che la GPU ce
# l'hanno. E' la forma esatta del difetto che questo blocco esisteva per
# prendere: un ripiego che non si dichiara, girato dall'altra parte.
if (-not $SenzaGpu) {
    $prov = & $pyexe -c @"
try:
    from core.onnx import preload
    preload()
    import onnxruntime as ort
    print(','.join(ort.get_available_providers()))
except Exception as e:
    print('errore:', e)
"@ 2>&1
    $haCuda = "$prov" -match "CUDAExecutionProvider"
    Esito "CUDA" $haCuda $(if ($haCuda) { "provider disponibile: Kokoro puo' girare su GPU" } else { "nessun provider CUDA ($prov). Kokoro su CPU costa 725 ms a battuta contro 207: usa tts.backend=piper" })
}

# -- 6. i modelli ------------------------------------------------------------
if (-not $SenzaModelli) {
    Write-Host "  ... scarico i modelli (Piper ed ECAPA, qualche centinaio di MB)" -ForegroundColor DarkGray
    & $pyexe -c @"
from speak.base import make_tts
from core.config import Config
cfg = Config()
cfg.tts.backend = 'piper'
try:
    make_tts(cfg.tts)
    print('voce ok')
except Exception as e:
    print('voce KO:', e)
"@ 2>&1 | Out-Null
    $ok = (Test-Path "models\piper") -or (Test-Path "models\kokoro")
    Esito "modelli di voce" $ok $(if ($ok) { "in models\" } else { "non scaricati: controlla la rete" })
}

# -- 7. la prova che conta: la suite -----------------------------------------
Write-Host "  ... eseguo la suite di verifica" -ForegroundColor DarkGray
$suite = & $pyexe -m tools.selftest 2>&1 | Select-Object -Last 3
$verde = "$suite" -match "verifiche verdi"
Esito "suite" $verde ("$suite" -split "`n" | Select-Object -Last 1)

# -- riepilogo ---------------------------------------------------------------
Write-Host "`n=== riepilogo ===" -ForegroundColor Cyan
$mancano = @($esiti.GetEnumerator() | Where-Object { -not $_.Value.ok })
if ($mancano.Count -eq 0) {
    Write-Host "Tutto a posto. Per partire:`n" -ForegroundColor Green
} else {
    Write-Host "$($mancano.Count) cose non ci sono. Il programma parte lo stesso, ma sapendo cosa manca:`n" -ForegroundColor Yellow
    foreach ($m in $mancano) { Write-Host "  - $($m.Key): $($m.Value.nota)" -ForegroundColor Yellow }
    Write-Host ""
}
Write-Host "  .\.venv\Scripts\python.exe -m tools.ui_qt --profile live" -ForegroundColor White
Write-Host "  (nella finestra: Scegli finestra -> Seleziona area -> Avvia)`n" -ForegroundColor DarkGray
