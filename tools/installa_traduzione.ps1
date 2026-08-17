# Installa la traduzione offline (Argos) **senza spegnere la GPU**.
#
# `pip install argostranslate` e basta fa due danni, misurati con `--dry-run`
# prima di installare:
#
#   1. tira `minisbd` -> `onnxruntime` (CPU), che scrive nella stessa cartella di
#      `onnxruntime-gpu`: la sintesi Kokoro passa da 207 a 725 ms a battuta, in
#      silenzio e con i log verdi;
#   2. tira `spacy` (~100 MB) che ad argos serve solo con un altro modo di
#      spezzare le frasi (il default e' `ARGOSTRANSLATE`, e l'import di spacy sta
#      dentro un `try`).
#
# Quello che non si evita: `argostranslate/sbd.py` importa `stanza`, che dipende
# da `torch`. Sono ~712 MB, per una traduzione che gira su CTranslate2 e torch non
# lo usa mai.
#
# Lo script e' rieseguibile: se e' gia' tutto a posto non fa niente.

$ErrorActionPreference = 'Stop'
$radice = Split-Path -Parent $PSScriptRoot
$py = Join-Path $radice '.venv\Scripts\python.exe'

if (-not (Test-Path $py)) {
    Write-Host "manca $py — ricostruire il venv prima" -ForegroundColor Red
    exit 1
}

Write-Host "`n== traduzione offline (Argos) ==" -ForegroundColor Cyan

# I due che vanno senza dipendenze, e il perche' e' scritto sopra.
& $py -m pip install --quiet "minisbd==0.9.5" --no-deps
& $py -m pip install --quiet "argostranslate==1.11.0" --no-deps
# Le dipendenze vere, a mano. `sacremoses` e `stanza` sono pinnate come le vuole
# argos: con la sacremoses 0.2.0 pip dichiara l'incompatibilita' e la lascia li'.
& $py -m pip install --quiet "ctranslate2==4.8.1" "sentencepiece==0.2.2" "sacremoses==0.1.1" "stanza==1.10.1" packaging

# **La verifica che conta non e' «il comando non ha dato errore».** ORT ripiega
# sulla CPU senza dirlo: se qui dentro e' rientrato `onnxruntime`, la GPU e'
# spenta e nessun altro numero lo mostrerebbe. Il controllo sta in un modulo e
# non qui dentro, cosi' lo esegue anche la suite.
& $py -m tools.controlla_traduzione
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nl'ambiente non e' a posto: vedere le righe qui sopra." -ForegroundColor Red
    exit 1
}
Write-Host "argostranslate a posto, GPU intatta." -ForegroundColor Green

# La coppia di lingue **non** si scarica qui: se la scarica da sola alla prima
# sessione, come i modelli di silero e di ECAPA (`translate/locale.py`). Chi la
# vuole gia' pronta, senza aspettare al primo Avvia:
Write-Host "`nper scaricarla adesso invece che al primo Avvia:" -ForegroundColor DarkGray
Write-Host "  .\.venv\Scripts\python.exe -m translate.locale --scarica en it" -ForegroundColor DarkGray
