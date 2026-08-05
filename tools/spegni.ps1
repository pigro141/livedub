# Chiude le applicazioni aperte e spegne il PC.
#
#   powershell -ExecutionPolicy Bypass -File tools\spegni.ps1
#   powershell -ExecutionPolicy Bypass -File tools\spegni.ps1 -Prova   # dice cosa farebbe
#
# **Prima chiede, poi insiste, e solo alla fine spegne.** Una chiusura brutale di
# un editor con del lavoro non salvato costa piu' di quanto valga qualunque
# script: si manda prima la richiesta gentile (`CloseMainWindow`, che e' la stessa
# cosa che fa il tasto X), si aspetta, e solo chi non se ne va viene terminato.
#
# **Ollama e il server dei modelli si fermano per primi**: tengono aperto un
# socket e dei modelli in VRAM, e vanno chiusi prima che Windows cominci a
# smontare tutto il resto.
#
# Lo spegnimento e' con `/t 20`: venti secondi in cui basta `shutdown /a` per
# annullare tutto. Uno script che spegne all'istante non lascia scampo a un
# ripensamento, e questo lo lascia.

[CmdletBinding()]
param(
    [switch]$Prova,          # non chiude e non spegne: elenca soltanto
    [int]$Attesa = 20        # secondi prima dello spegnimento
)

# I processi che vanno fermati per primi, in quest'ordine: servizi che tengono
# risorse (modelli in VRAM, socket) prima delle finestre normali.
$Servizi = @('ollama app', 'ollama')

# Le applicazioni con finestre. Non si tocca nient'altro: niente processi di
# sistema, niente esplorazioni "tutto quello che ha una finestra" — chiudere alla
# cieca un servizio di Windows e' il modo di trasformare uno spegnimento pulito in
# un riavvio che ripara il disco.
$Applicazioni = @(
    'chrome', 'msedge', 'firefox', 'brave',
    'Code', 'devenv', 'pycharm64', 'sublime_text', 'notepad', 'notepad++',
    'Spotify', 'Discord', 'Telegram', 'WhatsApp', 'Steam', 'EpicGamesLauncher',
    'GTA5', 'GTA5_Enhanced', 'PlayGTAV',
    'obs64', 'vlc', 'voicemeeter8x64', 'voicemeeterpro', 'voicemeeter'
)

function Ferma($nomi, [string]$etichetta, [int]$graziaMs = 4000) {
    $trovati = @()
    foreach ($n in $nomi) {
        $p = Get-Process -Name $n -ErrorAction SilentlyContinue
        if ($p) { $trovati += $p }
    }
    if (-not $trovati) {
        Write-Host "  $etichetta : niente da chiudere"
        return
    }
    Write-Host "  $etichetta : $(($trovati | Select-Object -ExpandProperty ProcessName -Unique) -join ', ')"
    if ($Prova) { return }

    # Prima la richiesta gentile: e' il tasto X, e lascia salvare.
    foreach ($p in $trovati) {
        try { $null = $p.CloseMainWindow() } catch {}
    }
    Start-Sleep -Milliseconds $graziaMs

    # Poi, solo a chi e' rimasto.
    foreach ($p in $trovati) {
        try {
            $p.Refresh()
            if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force -ErrorAction SilentlyContinue }
        } catch {}
    }
}

Write-Host ""
Write-Host "== chiusura applicazioni ==" -ForegroundColor Cyan
Ferma $Servizi 'servizi (ollama)' 2000
Ferma $Applicazioni 'applicazioni' 5000

Write-Host ""
if ($Prova) {
    Write-Host "prova: non e' stato chiuso niente e non si spegne." -ForegroundColor Yellow
    exit 0
}

Write-Host "== spegnimento fra $Attesa secondi ==" -ForegroundColor Cyan
Write-Host "  per annullare:  shutdown /a" -ForegroundColor Yellow
shutdown /s /t $Attesa /c "livedub: spegnimento richiesto. Annulla con: shutdown /a"
