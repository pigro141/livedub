# La tua prova, e cosa guardare

Questo file e' il foglio della **prova d'ascolto**: come si accende, cosa
guardare, e cosa mi serve nel tuo report. La suite e' verde (1416 verifiche) ma
la suite non sente niente: ogni difetto serio di questo progetto e' stato trovato
dal tuo orecchio, con la suite verde.

---

## Aggiornamento dell'11 agosto, a sera: tre di queste domande hanno gia' una risposta

La catena e' stata accesa **dal vivo in autonomia** — una registrazione a schermo
intero in Chrome al posto del gioco, cattura vera, OCR vero, audio vero da
Voicemeeter — quindi non serve che tu accenda niente per sapere queste tre cose.

**La compressione (punto 3): si e' staccata dal tetto.** `dub.rate_x1000` al p50
vale **1000** invece di 1250, ed era la previsione scritta *prima*: se fosse
rimasta a 1250 la diagnosi su `accepted_delay_ms` era sbagliata. Non lo era.
Latenza p50 **665 ms** e `mix.underrun` **0**, cioe' i numeri dichiarati.

**Il difetto che resta e che si sente**: l'HUD del gioco (*«Sali sul \[tasto]»*)
sta nella stessa fascia dei sottotitoli, il glifo del tasto l'OCR lo legge come
spazzatura **diversa a ogni fotogramma**, e ogni fotogramma apre una battuta
nuova. Misurato: **8 battute su 17** in una passata dal vivo, e **11 su 46**
rigiocando lo stesso pezzo dal file — quindi non e' la cattura, e' la catena.
Sono le battute che senti come parole tronche una sull'altra, tutte accelerate al
massimo. **Aspetto la tua scelta fra due strade** (stanno in fondo a
`SviluppoProgetto.md`), perche' una delle due tocca una soglia che vale per tutti
i sottotitoli e non solo per l'HUD.

**Chi parla, sulle scene di battibecco, non lo riconosce quasi mai** — e non e'
un difetto del vivo: sullo stesso tratto il banco fa uguale (81% contro 78% di
voce neutra), e il caso nullo dice che non c'e' soglia da tarare. Serve piu'
parlato per battuta, non un numero diverso.

---

## Come si accende

```powershell
cd C:\Users\filde\Documents\!code\CLAUDE\livedub

# sottotitoli italiani -> voce italiana (il caso principale)
powershell -ExecutionPolicy Bypass -File tools\prova.ps1

# sottotitoli italiani -> voce inglese, con il sottotitolo tradotto a schermo
powershell -ExecutionPolicy Bypass -File tools\prova.ps1 -Traduci

# parte da sola, con l'area del profilo (niente tasti da premere)
powershell -ExecutionPolicy Bypass -File tools\prova.ps1 -Traduci -Avvia

# per vedere solo cosa farebbe, senza partire
powershell -ExecutionPolicy Bypass -File tools\prova.ps1 -Traduci -Prova

# una variante, senza riscrivere la riga a mano (-Set e' ripetibile, e viene stampato)
powershell -ExecutionPolicy Bypass -File tools\prova.ps1 -Traduci `
    -Set translate.background_mode=riquadro
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

**E l'overlay adesso si fotografa.** Era dichiarato fuori da *tutte* le catture
perche' rientrava nel fotogramma dato all'OCR — con due prezzi: non lo vedeva
nemmeno chi registra, e non era diagnosticabile. Scegliendo **la finestra del
gioco** invece dello schermo non ci rientra affatto, quindi quella cura e' stata
tolta: uno screenshot lo prende, e chi registra lo vede. Se scegli «Tutto lo
schermo» l'esclusione torna da sola, e li' vale ancora la vecchia regola.

Quindi **mandami pure gli screen**: valgono piu' di qualunque descrizione.

**Se non succede niente**, guarda la prima riga nel log della finestra: dice
quale cattura sta usando, e se quella veloce non restituisce fotogrammi lo scrive
e passa a `mss` da sola dopo due secondi. Su questa macchina, con il desktop,
`dxcam` restituisce **zero** fotogrammi su 1071 — col gioco acceso puo' andare
diversamente, e per questo il ripiego e' automatico invece che una scelta.

---

## 0. La domanda di adesso: **blur o riquadro?**

E' l'unica cosa che i numeri non possono decidere, e ti riguarda direttamente.

Hai detto che il blur va in differita. Era vero, e in parte era colpa nostra: il
ritaglio dei pixel da sfocare aspettava che l'OCR avesse finito di leggere — 84
ms al p50, 137 al massimo, cioe' quattro fotogrammi di ritardo che non c'entravano
niente. Adesso parte subito dopo la cattura, e il ritardo che resta si misura:
`overlay.ritardo` in fondo a `report.txt`, **p50 20-23 ms**.

**Ma a zero non ci arriva, e non e' pigrizia.** Far vedere pixel del gioco vuol
dire copiarli — cattura, nostro processo, finestra, compositore — e quella catena
ha un pavimento. Ho provato a farlo fare a Windows (che i pixel ce li ha gia'):
su questa versione le due funzioni che dovrebbero sfocare **tingono e basta**,
misurato.

Quindi ci sono due strade, e scegli tu:

| | ritardo | come si vede |
|---|---|---|
| `blur` (default) | resta un residuo | il gioco si intravede, piu' discreto |
| `riquadro` | **nessuno, per costruzione** | tinta piatta del colore della scena, copre meglio ma si nota di piu' |

Il riquadro non ha ritardo perche' una tinta piatta non ha struttura da mostrare
in ritardo. Il colore non e' nero: e' la **mediana dei pixel che sta coprendo**,
ripresa a ogni fotogramma, quindi si intona alla scena.

Si prova cosi':

```powershell
powershell -ExecutionPolicy Bypass -File tools\prova.ps1 -Traduci `
    -Set translate.background_mode=riquadro
```

**Cosa mi serve**: quale dei due preferisci, e se col blur il ritardo si vede
ancora **in guida** (e' li' che si nota). Se dici «il riquadro si vede troppo ma
il blur e' ancora indietro», c'e' una terza strada non ancora provata: alzare
molto `translate.blur_strength`. Dei pixel abbastanza sfocati non si datano,
quindi il ritardo smette di vedersi pur restando.

---

## 0b. E i doppioni, che tornavano

Avevi ragione: la stessa frase usciva due volte. Il cancello anti-ripetizione
c'era e funzionava, e ha smesso quando e' arrivata la traduzione — confrontava la
frase italiana appena letta con quella gia' **detta in inglese**, cioe' due cose
che non si somigliano mai. Nella tua sessione il contatore diceva 0 soppressioni
con due doppioni identici a schermo; adesso ne sopprime 6 sulla stessa scena.

**Cosa guardare**: che non ne escano piu' — e, all'opposto, che non sparisca una
battuta che un personaggio ripete **davvero**. Il secondo difetto sarebbe peggiore
del primo, e si vede solo all'ascolto.

---

## 1. La grafica — la forma finale e' quella che hai proposto tu

**Un rettangolo, sfocato dal vivo, col testo sopra.** Il rettangolo circoscrive
il sottotitolo letto dall'OCR e si calcola **una volta** alla comparsa (se no
balla); la sfocatura dentro si rifa' a **ogni fotogramma** sui pixel correnti (se
no e' una toppa di immagine vecchia incollata su una scena che si muove); e
sparisce quando l'OCR non legge piu' quel sottotitolo.

Le due forme provate prima erano piu' complicate e sbagliate, e i difetti che
hai visto venivano da li': sfocare tutta la ROI dava una fascia larga mezzo
schermo; cancellare riga per riga ricostruendo lo sfondo, e inseguire
l'inchiostro fotogramma per fotogramma, dava le toppe accanto al testo e le
macchie sull'asfalto — perche' su una scena luminosa dell'inchiostro si trova
sempre da qualche parte.

**Quanto restava a schermo il tradotto**, stesso video e stessa catena, cambia
solo chi decide quando sparire:

| chi decide | p50 | p95 | max | oltre 5 s |
|---|---|---|---|---|
| l'inchiostro (com'era) | 4,9 s | 20,8 s | **23,5 s** | 21 su 43 |
| il lettore (adesso) | 2,7 s | 5,0 s | 7,1 s | 2 su 43 |

I 23,5 secondi sono i diciotto che si vedevano nel tuo video.

## 1b. Come c'ero arrivato prima (storia, non istruzioni)

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

    --set translate.background_mode=blur       (default: il rettangolo sfocato)
    --set translate.background_mode=riquadro   (rettangolo pieno, stretto sulla riga)
    --set translate.background_mode=nessuno    (non si cancella niente)
    --set translate.font_frac=0.045            (forza la taglia invece di copiarla)
    --set translate.color=#ffcc00              (forza il colore)

## 2. Adesso si cattura **la finestra del gioco**, non lo schermo

E' il cambiamento piu' grosso, ed e' anche la spiegazione piu' probabile del
«non vedo la traduzione».

Catturando lo schermo intero, la nostra finestra del tradotto finiva dentro il
fotogramma che davamo all'OCR — misurato, il 100% dei suoi pixel. Per impedirlo
l'avevo dichiarata **fuori da ogni cattura**, e quella cura aveva due prezzi che
si pagavano insieme: non la vedeva chi registra, e non era piu' fotografabile,
quindi non era piu' nemmeno diagnosticabile.

Scegliendo la finestra, il problema non si cura: **non esiste**. Verificato due
volte: una finestra rossa messa sopra a quella catturata non entra nel fotogramma
(0,000 dei suoi pixel), e con la catena intera l'OCR ha letto zero righe che
fossero nostre su quattro. Quindi l'overlay torna una finestra normale.

Nella finestra di livedub: **Scegli finestra** -> il gioco -> *Seleziona area* ->
*Avvia*. Il primo della lista e' quasi sempre quello giusto. Se il gioco si
sposta, il sottotitolo lo segue da solo.

**Se ancora non lo vedi**, nel log della finestra ci sono le due righe che
dividono il problema in due:

- `cattura: finestra` (o `mss`/`dxcam`) — dice **cosa** stiamo catturando;
- `overlay 1516x221+522+1213 visibile` — dice che il programma **crede** di
  averlo disegnato. Se questa riga c'e' e a schermo non vedi niente, prova
  `-Opaco`: toglie il colore trasparente e la finestra diventa normale.

## 3. La compressione## 3. La compressione — alzata la scusa, e serve il tuo giro per chiuderla

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

## 4. Quello che resta aperto e non dipende da me

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
