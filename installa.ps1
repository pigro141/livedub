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

# **`2>&1` su un eseguibile nativo dichiara fallita un'installazione riuscita.**
# In Windows PowerShell 5.1 ogni riga che un `.exe` scrive su stderr viene
# avvolta in un `NativeCommandError`; con `$ErrorActionPreference = "Stop"` quello
# e' un errore **terminante**, quindi basta un avviso stampato da un comando
# andato a buon fine (exit code 0) perche' questo script muoia con `exit 1` dopo
# aver scritto tutti i passi in verde. Riprodotto: la suite ne stampa uno di
# serie, e l'ultima cosa che leggeva chi aveva appena installato tutto era un
# errore.
#
# Qui l'unione dei due flussi serve — si vuole leggere anche cio' che il comando
# lamenta — quindi non si toglie il `2>&1`: si toglie la parte «terminante»,
# nell'unico punto in cui il comando gira. Fuori resta `Stop`, che e' quello che
# ferma lo script quando a fallire e' *questo* file.
function Esegui([scriptblock]$comando) {
    $prima = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { & $comando 2>&1 } finally { $ErrorActionPreference = $prima }
}

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
        $v = Esegui ([scriptblock]::Create("$c --version"))
        if ($v -match "3\.11") { $py = $c; break }
    } catch { }
}
if (-not $py) {
    Esito "Python 3.11" $false "non trovato: installa Python 3.11 (https://www.python.org/downloads/)"
    Write-Host "`nSenza Python 3.11 non si va avanti.`n" -ForegroundColor Red
    exit 1
}
Esito "Python 3.11" $true (Esegui ([scriptblock]::Create("$py --version")))

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
if (-not $ok) {
    # **Non si va avanti misurando un ambiente a meta'.** Tutto quello che viene
    # dopo — la CUDA, i modelli, la suite — risponderebbe su un venv incompleto, e
    # le sue risposte sembrerebbero difetti del programma.
    Write-Host "`nle dipendenze non sono entrate: le righe di pip qui sopra dicono perche'.`n" -ForegroundColor Red
    exit 1
}

# -- 3b. i quattro che vanno senza dipendenze --------------------------------
# `rapidocr-onnxruntime`, `piper-tts`, `supertonic` e `kokoro-onnx` chiedono tutti
# `onnxruntime` — la ruota CPU — che accanto a `onnxruntime-gpu` **spegne la CUDA
# in silenzio**: 725 ms a battuta invece di 207, con i log verdi. Il perche' per
# esteso, con la misura, sta in `requirements-nodeps.txt`.
& $pyexe -m pip install -r requirements-nodeps.txt --no-deps --quiet
$ok = $LASTEXITCODE -eq 0
Esito "lettore e voci" $ok $(if ($ok) { "da requirements-nodeps.txt, senza dipendenze" } else { "pip ha fallito" })
if (-not $ok) {
    Write-Host "`nsenza il lettore e la voce il programma non doppia niente.`n" -ForegroundColor Red
    exit 1
}

# -- 3c. e la prova che conta non e' «il comando e' finito» ------------------
# Se `onnxruntime` (CPU) si e' intrufolato lo stesso — una dipendenza nuova, un
# `pip install` fatto a mano — **nessun errore lo direbbe**: la sintesi diventa
# tre volte piu' lenta e basta. La regola sta in un modulo, non qui, cosi' la
# esegue anche la suite.
$sorgente = @"
import importlib.metadata as md
nomi = {(d.metadata['Name'] or '').lower() for d in md.distributions() if d.metadata['Name']}
print('DOPPIO' if 'onnxruntime' in nomi else 'SOLO-GPU')
"@
$doppio = Esegui { & $pyexe -c $sorgente }
$soloGpu = "$doppio" -match "SOLO-GPU"
Esito "onnxruntime" $soloGpu $(if ($soloGpu) { "solo il pacchetto GPU, com'e' giusto" } else { "c'e' anche la ruota CPU accanto a onnxruntime-gpu: la CUDA e' spenta. Toglierla con `pip uninstall onnxruntime` e rimettere onnxruntime-gpu[cuda,cudnn]==1.28.0" })

# -- 4. OneOCR ---------------------------------------------------------------
# Non ridistribuibile: si copia dalla macchina, dove l'utente ce l'ha gia' con la
# sua licenza Windows. Si veda docs/LICENZE.md.
if (Test-Path "models\oneocr\oneocr.onemodel") {
    Esito "OneOCR" $true "gia' presente"
} else {
    Esegui { & $pyexe -m tools.fetch_oneocr } | Out-Null
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
    # **E il provider si chiede alla sessione, non all'elenco.**
    # `get_available_providers()` elenca quelli **compilati dentro** onnxruntime
    # e risponde `CUDAExecutionProvider` anche dove le DLL di NVIDIA non ci sono:
    # questo installatore diceva percio' «Kokoro puo' girare su GPU» su una
    # macchina dove Kokoro sarebbe partito sulla CPU a 725 ms a battuta.
    # `core.onnx.cuda_ottenuta` apre una sessione da settanta byte e guarda cosa
    # ha preso — un ripiego che non si dichiara e' peggio di un errore.
    $sorgente = @"
try:
    from core.onnx import cuda_ottenuta
    ok, com_e = cuda_ottenuta('installa.ps1')
    print(('si' if ok else 'no') + ':' + com_e)
except Exception as e:
    print('no: errore:', e)
"@
    $prov = Esegui { & $pyexe -c $sorgente }
    $haCuda = "$prov" -match "^si:"
    Esito "CUDA" $haCuda $(if ($haCuda) { "provider ottenuto su una sessione vera: Kokoro puo' girare su GPU" } else { "la sessione non ha preso la CUDA ($prov). Kokoro su CPU costa 725 ms a battuta contro 207: usa tts.backend=piper" })
}

# -- 6. i modelli ------------------------------------------------------------
if (-not $SenzaModelli) {
    Write-Host "  ... scarico i modelli (Piper ed ECAPA, qualche centinaio di MB)" -ForegroundColor DarkGray
    $sorgente = @"
from speak.base import make_tts
from core.config import Config
cfg = Config()
cfg.tts.backend = 'piper'
try:
    make_tts(cfg.tts)
    print('voce ok')
except Exception as e:
    print('voce KO:', e)
"@
    Esegui { & $pyexe -c $sorgente } | Out-Null
    $ok = (Test-Path "models\piper") -or (Test-Path "models\kokoro")
    Esito "modelli di voce" $ok $(if ($ok) { "in models\" } else { "non scaricati: controlla la rete" })
}

# -- 7. la prova che conta: la suite -----------------------------------------
Write-Host "  ... eseguo la suite di verifica" -ForegroundColor DarkGray
$suite = Esegui { & $pyexe -m tools.selftest } | Select-Object -Last 3
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

# **La traduzione offline non si installa qui, e non e' una dimenticanza.** Costa
# ~3 GB (`stanza` tira `torch`, che la traduzione non usa mai) e su GTA V in
# italiano non serve: `translate.enabled` e' false di serie. Metterla qui vorrebbe
# dire far pagare tre giga a chiunque installi il programma, per una cosa che
# quasi nessuno accende.
#
# Serve quando serve, ed e' esattamente il meccanismo che il programma ha gia': il
# **passo 6 della guida** («Misura questo PC») guarda cosa manca, dice **quanto
# pesa prima** che uno decida, e — da oggi — la **installa**, eseguendo
# `tools/installa_traduzione.ps1`, cioe' l'unico posto in cui le opzioni giuste
# stanno scritte. Rimandare li' invece di stampare un comando qui vuol dire un
# posto solo che risponde a questa domanda, invece di due che prima o poi si
# contraddicono.
Write-Host "La traduzione offline non e' installata: si accende dalla guida," -ForegroundColor DarkGray
Write-Host "al passo «Misura questo PC», che dice quanto pesa prima di scaricarla.`n" -ForegroundColor DarkGray
