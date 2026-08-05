# La tua prova, e cosa guardare

Questo file e' il foglio della **prova d'ascolto**: come si accende, cosa
guardare, e cosa mi serve nel tuo report. La suite e' verde (1122 verifiche) ma
la suite non sente niente: ogni difetto serio di questo progetto e' stato trovato
dal tuo orecchio, con la suite verde.

---

## Come si accende

```powershell
cd C:\Users\filde\Documents\!code\CLAUDE\livedub

# sottotitoli italiani -> voce italiana (il caso principale)
powershell -ExecutionPolicy Bypass -File tools\prova.ps1

# sottotitoli italiani -> voce inglese, con il sottotitolo tradotto a schermo
powershell -ExecutionPolicy Bypass -File tools\prova.ps1 -Traduci

# per vedere solo cosa farebbe, senza partire
powershell -ExecutionPolicy Bypass -File tools\prova.ps1 -Traduci -Prova
```

Lo script controlla **prima** le tre cose che altrimenti si scoprono a gioco
avviato: che il venv ci sia, che esista la scheda di cattura `voicemeeter`, e —
se traduci — che Ollama sia acceso e abbia `translategemma:4b` (se e' spento lo
accende lui). Poi stampa la configurazione per esteso, cosi' il report dice cosa
e' stato provato davvero.

Nella finestra: **Seleziona area** sui sottotitoli del gioco, poi **Avvia**. Alla
fine **Ferma**, e la sessione finisce in `runs\<data-ora>` con dentro l'audio,
gli eventi e il riepilogo.

**Il gioco deve stare in finestra senza bordi, non a schermo intero esclusivo.**
Sopra un fullscreen esclusivo nessuna finestra puo' comparire, e l'overlay non si
vedrebbe — senza che niente lo dica.

---

## 1. La grafica — rifatta da capo, e stavolta l'ho guardata io in MP4

Avevi ragione su tutto, e il difetto peggiore l'hai trovato tu.

**La nostra finestra finiva dentro la cattura.** La catena fotografa lo schermo
30 volte al secondo per darlo all'OCR, e la finestra del tradotto **sta sullo
schermo**: misurato, il 100% dei suoi pixel entrava nel fotogramma, con tutti e
due i backend. L'OCR non leggeva piu' il gioco, leggeva noi — ed e' quello che ti
saltava le righe. Adesso la finestra e' dichiarata **fuori dalla cattura** con la
stessa funzione di Windows con cui le app nascondono le password dalla
condivisione schermo. Rimisurato dopo: **0%**.

**Si cancella la scrittina, non il riquadro.** Prima si spegneva una fascia larga
mezzo schermo. Adesso si tocca **solo la riga che l'OCR ha letto**, e il resto
della finestra e' un buco trasparente da cui si vede il gioco intatto. E non si
sfoca: si **ricostruisce lo sfondo** al posto delle lettere (inpaint), perche' la
domanda giusta non era «renderla illeggibile» ma «farla sembrare mai esistita» —
sopra ci va la nostra, e due sottotitoli sovrapposti si vedono anche quando uno
e' sfocato.

**Il testo copia quello del gioco, e non c'e' nessun numero scritto a mano.**
Misura e colore si prendono dal sottotitolo che si sta coprendo, battuta per
battuta: su GTA V viene bianco della stessa taglia, su un gioco che colora i
personaggi verrebbe del loro colore, su un gioco che scrive piu' grande verrebbe
piu' grande. Restano forzabili (`translate.font_frac`, `translate.color`), e
l'interfaccia li esporra'.

**Il font era troppo grosso, e adesso so perche'.** Confrontavo l'altezza della
riga con l'altezza di `Ag` — che va dall'ascendente al discendente, mentre `Ciao,
Lamar!` e' alto solo quanto le maiuscole: chiedevo un carattere alto quanto una
riga intera per ottenere delle sole maiuscole, il 40% di troppo. Adesso il
confronto e' sulla **larghezza** del testo che l'OCR ha letto: stesse lettere,
stessa grandezza. La verifica e' un andata e ritorno — si disegna un sottotitolo
finto a 26 punti e si devono ritrovare 26.

**La taglia e' una sola per tutta la sessione**: si tiene la mediana delle
battute viste, perche' un gioco non cambia taglia da solo e una taglia che balla
e' rumore (la dissolvenza con cui il sottotitolo compare, l'OCR che legge una
parola in piu').

**Il testo non si muove piu'.** Era la cosa peggiore: ridisegnavo tutto a ogni
fotogramma, quindi il riquadro inseguiva l'immagine come un tracker, tremava e
nei fotogrammi di dissolvenza spariva. Adesso taglia, colore e posizione si
decidono **quando la battuta compare** e non si toccano piu'. Solo la
cancellatura sotto si rinfresca dieci volte al secondo, se no — provato e
guardato — resta una toppa di immagine vecchia mentre la scena si muove.

**E la finestra resta finche' resta il sottotitolo del gioco**, non finche' dura
la nostra voce: prima spariva prima, e per l'ultimo pezzo di battuta tornava a
vedersi l'italiano.

### Guardalo prima di accendere il gioco

    .\.venv\Scripts\python.exe -m tools.overlay_mp4 testGameplayFattoDaMe.mp4 runs\<passata> `
        --profile gtav --offset 1240 --start 1240 --end 1285 --out runs\ov\overlay.mp4

Questo monta un video con **lo stesso codice che disegna la finestra dal vivo**,
quindi non e' un disegno: e' la grafica. Da adesso i giri di correzione li faccio
qui e ti mando il video, invece di farti accendere tutto ogni volta.

**Quello che il video non puo' dire**, e che resta da vedere a schermo: se la
finestra ruba i clic, se sfarfalla quando si sposta, se il gioco la lascia sopra
di se', e — la piu' importante — **se adesso l'OCR non salta piu' le righe**.

Puoi cambiare come copre:

    --set translate.background_mode=cancella   (default: la riga sparisce)
    --set translate.background_mode=blur       (sfocata: resta una fascia grigia)
    --set translate.background_mode=riquadro   (rettangolo pieno, stretto sulla riga)
    --set translate.background_mode=nessuno    (non si cancella niente)
    --set translate.font_frac=0.045            (forza la taglia invece di copiarla)
    --set translate.color=#ffcc00              (forza il colore)

## 2. La compressione — alzata la scusa, e serve il tuo giro per chiuderla

`dub.rate_x1000` restava a **1250 su tutti i percentili**: ogni battuta
schiacciata al massimo, con il parlato che riempiva meta' scena.

La causa e' quella che sospettavo, e adesso e' misurata. Il budget di una battuta
e' `finestra prevista - (tempo gia' passato - scusa)`. Con la traduzione sulla
strada critica il tempo gia' passato e' **1,6-1,7 s** (misurato dalle tue due
sessioni), e la scusa valeva **250 ms**: al budget venivano tolti quasi un
secondo e mezzo di una finestra che ne dura due.

Rigiocando la programmazione delle tue due sessioni con scuse diverse (stessi
tempi veri, stesse durate: cambia solo la scusa) — la peggiore delle due:

| scusa | compressione p50 | battute al tetto |
|---|---|---|
| 250 ms (com'era) | 1,250 | 100% |
| 900 ms | 1,250 | 62% |
| 1000 ms | 1,182 | 25% |
| **1250 ms (adesso)** | **1,000** | 17% |
| 1600 ms | 1,000 | 12%, ma la coda cresce |

Il controllo che rende credibile quel conto: alla scusa che quelle sessioni
avevano davvero, il conto riproduce esattamente quello che era stato registrato.

**Il numero che ti chiedo di guardare**, nel riepilogo a fine sessione:
`dub.rate_x1000` **deve staccarsi da 1250** almeno al p50. Se resta 1250 su tutti
i percentili anche adesso, la diagnosi era sbagliata e il vincolo sta altrove —
e lo scrivo qui prima della tua prova apposta, perche' una previsione fatta dopo
non puo' perdere.

E poi giudicalo a orecchio: la voce dovrebbe articolare invece di correre. In
cambio si accettano fino a ~370 ms in piu' sul ritardo peggiore.

**Senza traduzione non peggiora**, che era il rischio: misurato sulla
registrazione, la compressione mediana non si muove, quella al p95 migliora
(1,250 -> 1,133) e gli sfori si dimezzano.

## 3. Quello che resta aperto e non dipende da me

- **`translate.preserve_register`**: TranslateGemma ammorbidisce le parolacce.
  Con il registro chiesto esplicitamente fa 2-3 su 6, Google 6 su 6 ma manda
  ogni sottotitolo ai suoi server. Se traduci e ti sembra che dica un'altra
  cosa, e' questo, non l'OCR.
- **La correzione OCR resta spenta**, con i numeri in mano: `translategemma:4b`
  fa 5 su 8 ma **1784 ms per parola**, contro un guadagno massimo di una parola
  su settanta.
- **Il nome del parlante** (`label.form`) e' provato solo su testo sintetico:
  GTA V i nomi non li scrive. Il contatore `vision.label.hit` dira' subito se il
  formato dichiarato e' quello giusto, quando avrai un gioco che li scrive.
- **Le voci femminili**: la taratura del genere non e' mai stata provata su una
  donna, perche' nella registrazione non ce n'e' una.

---

## Cosa mi serve nel report

Per ogni cosa che non va, la sola informazione che vale piu' di tutte le altre e'
**il secondo in cui l'hai sentita**: `runs\<data-ora>` si riapre con

```powershell
.\.venv\Scripts\python.exe -m tools.reopen runs\<data-ora> <secondo>
```

e da li' si vede cosa aveva letto l'OCR, chi credeva che parlasse, che voce gli
aveva dato e quanta fretta gli aveva chiesto. Un'impressione senza il secondo
costa mezza sessione; il secondo la chiude in cinque minuti.
