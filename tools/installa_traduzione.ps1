# Installa la traduzione offline (Argos) **senza spegnere la GPU e senza torch**.
#
# ## Serve ancora?
#
# Quasi mai. Dal 4 settembre i cinque pacchetti stanno in `requirements.txt` e
# `requirements-nodeps.txt`, quindi arrivano ricostruendo l'ambiente come tutto
# il resto, e viaggiano **dentro l'eseguibile**. Questo script resta per i venv
# costruiti prima, e perche' e' l'unico posto in cui le opzioni sono scritte una
# volta sola — le legge anche `core/banco.py`, che lo esegue invece di
# reinventarle.
#
# ## Le due trappole, e la terza che e' stata tolta
#
# `pip install argostranslate` e basta fa due danni, misurati con `--dry-run`
# prima di installare:
#
#   1. tira `minisbd` -> `onnxruntime` (CPU), che scrive nella stessa cartella di
#      `onnxruntime-gpu`: la sintesi Kokoro passa da 207 a 725 ms a battuta, in
#      silenzio e con i log verdi;
#   2. tira `spacy` (~100 MB) che ad argos serve solo con un altro modo di
#      spezzare le frasi.
#
# La terza era `stanza`, e con lui **3037,5 MB di torch** — misurati in
# `site-packages`, contro i 65,8 di tutto il resto messo insieme. Non c'e' piu':
# stanza ad Argos serve solo per spezzare le frasi, e `translate/locale.py`
# chiede `ARGOS_CHUNK_TYPE=MINISBD`, che fa lo stesso lavoro con un `.onnx` da
# 178 KB. Il caso nullo e' misurato li': 12 battute su 12 identiche carattere per
# carattere, prima battuta 201 ms invece di 1422.
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
# Le dipendenze vere, a mano. `sacremoses` e' pinnata come la vuole argos: con la
# 0.2.0 pip dichiara l'incompatibilita' e la lascia li'.
# **Le versioni sono quelle che Smart App Control lascia caricare**, provate in un
# venv nuovo: `ctranslate2` 4.8.1 e 4.4.0 sono bloccate e la 4.6.0 no,
# `sentencepiece` 0.2.2 e' bloccata e la 0.2.0 no.
& $py -m pip install --quiet "ctranslate2==4.6.0" "sentencepiece==0.2.0" "sacremoses==0.1.1" packaging filelock

# **La verifica che conta non e' «il comando non ha dato errore».** ORT ripiega
# sulla CPU senza dirlo: se qui dentro e' rientrato `onnxruntime`, la GPU e'
# spenta e nessun altro numero lo mostrerebbe. Il controllo sta in un modulo e
# non qui dentro, cosi' lo esegue anche la suite — e dice anche **quale**
# spezza-frasi e' in uso, che e' la differenza fra 66 MB e tre giga.
& $py -m tools.controlla_traduzione
if ($LASTEXITCODE -ne 0) {
    Write-Host "`nl'ambiente non e' a posto: vedere le righe qui sopra." -ForegroundColor Red
    exit 1
}
Write-Host "argostranslate a posto, GPU intatta, niente torch." -ForegroundColor Green

# La coppia di lingue **non** si scarica qui: se la scarica da sola alla prima
# sessione, come i modelli di silero e di ECAPA (`translate/locale.py`). Chi la
# vuole gia' pronta, senza aspettare al primo Avvia:
Write-Host "`nper scaricarla adesso invece che al primo Avvia:" -ForegroundColor DarkGray
Write-Host "  .\.venv\Scripts\python.exe -m translate.locale --scarica en it" -ForegroundColor DarkGray
