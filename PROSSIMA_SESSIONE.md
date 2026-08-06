# Prompt per la prossima sessione

Copia da qui in giù.

---

Lavoro su **livedub** (`C:\Users\filde\Documents\!code\CLAUDE\livedub`), doppiaggio
italiano dal vivo dei sottotitoli dei videogiochi.

## Come si conosce questo progetto

**Il grafo è la memoria.** In `graphify-out/graph.json` c'è la mappa della
codebase. Per qualunque domanda architetturale si usa `graphify query "<domanda>"`
**prima** di partire a grep. Si riaggiorna con `/graphify . --update` dopo
modifiche grosse, non a ogni task.

Poi `CLAUDE.md`, che ha l'architettura e le regole di metodo. **Non leggere il
README per intero.**

## Come voglio che tu lavori

- **Scrivi solo quando hai finito.** Non commentare ogni passo.
- **Descrivi in modo semplicissimo ma dettagliato** cosa hai fatto.
- **Non sprecare token.**
- **Prima di azzardare, chiedi.**

## Dove siamo

Suite verde a **1164 verifiche**. L'ultima sessione è partita da un video di
debug registrato dall'utente ed è stata tutta **grafica dell'overlay dal vivo**:
quattro difetti trovati guardando i suoi fotogrammi e il suo log, non il codice.

**Il vivo è stato provato due volte**, in `runs/2026-08-06_15-34-16` (blur) e
`runs/2026-08-06_15-51-18` (riquadro). Da lì vengono tutti i numeri qui sotto.

## Le cinque cose che questa sessione ha cambiato

**1. Il riquadro sfocato non si allarga più, e si posa dove l'OCR ha letto.**
Nel log dell'utente andava a `1515x390` — l'intera fascia d'analisi per una riga
da 45 px — col raggio della sfocatura a 55,8 invece di 12. Due cause: la
geometria si ricercava nei pixel **2310 ms dopo** la lettura (scena cambiata,
originale sparito, si trovava scenario), e il filtro delle bande guardava **solo**
la sovrapposizione orizzontale. Adesso `SpokenLine.boxes`/`ink` portano a valle i
rettangoli validati dal lettore, finiscono anche in `events.jsonl`, e **vivo e
MP4 prendono la geometria dalla stessa fonte**. Misurato dal vivo dopo: altezza
del riquadro p50 28-39 px, una sola sopra i 100 su 30 righe.

**2. Il blur non aspetta più l'OCR.** Il ritaglio stava in fondo al giro video:
per spedire dei pixel da sfocare aspettava che l'OCR avesse letto — `vision.ocr`
a 84 ms al p50 e 137 al massimo. Adesso parte subito dopo `grab()`. E
`overlay.ritardo`, che veniva misurato a ogni giro e **buttato**, finisce nel
report: **p50 20-23 ms, p95 39, max 70**.

**3. I doppioni: il cancello confrontava due lingue.** `_gia_detta` riceve la
battuta prima che `_speak` la traduca (italiano), le battute già dette la
conservano tradotta (inglese): `abbracciami` contro `hugme`, quindi **non poteva
scattare mai**. `dub.repeated` era a 0 con due doppioni identici a schermo; dopo
la cura, **6** sulla stessa scena.

**4. Il blur a ritardo zero non si può fare, e la modalità che lo è esisteva
già.** Provato se può sfocare il compositore invece di noi: su Windows 11 26200
`ACCENT_ENABLE_BLURBEHIND` e `ACCENT_ENABLE_ACRYLICBLURBEHIND` **tingono e
basta** (lo scalino chiaro/scuro dietro passa da 99,9 a 3,8 e 9,5).
`background_mode="riquadro"` invece il ritardo non ce l'ha per costruzione, e
adesso il suo colore è la mediana dei pixel coperti invece di un nero fisso.

**5. `prova.ps1` accetta `-Set sezione.campo=valore`**, ripetibile e stampato.

## La domanda aperta, ed è dell'utente non dei numeri

**Blur o riquadro?** Il blur mostra il gioco ma ha un ritardo residuo che non si
può togliere; il riquadro non ha ritardo ma si nota di più. L'utente ha provato
tutti e due e **il suo giudizio non è ancora arrivato**. Non cambiare il default
prima di quello.

La terza strada, se dice «il riquadro si vede troppo ma il blur è ancora in
ritardo»: alzare molto `translate.blur_strength`. Dei pixel abbastanza sfocati
non sono databili, quindi il ritardo smette di vedersi pur restando. Non è stata
provata.

## Il difetto che resta, e che nessun filtro può togliere

**La riga di testo si salda a ciò che ha attorno.** Su fondo chiaro `find_bands`
non affianca la riga al chiaro vicino: ci si fonde — misurato, una banda alta
**186 px che conteneva** un sottotitolo da 45. Il riquadro allora cresce con lei.
Le cure ci sono (ancora scelta per vicinanza al centro dell'area, altezza di
riferimento limitata dal corpo del carattere, tetto duro sul riquadro) ma la
causa a monte è **l'area disegnata troppo alta**: con `respiro = 0.6*rh`, un
rettangolo alto un sesto dello schermo dà una fascia di 391 px per una riga da
45. La UI adesso avvisa sopra 0,12. Se il difetto torna, è lì che si guarda.

## Le due cose che l'ultima sessione ha lasciato in giro

- `dub.rate_x1000` sta a **1250 dal p95 in su** in entrambe le sessioni (p50
  1000-1040). Un numero inchiodato al tetto, in questo progetto, non è mai una
  coincidenza. Non è stato indagato.
- L'OCR sporca il testo e il traduttore ci costruisce sopra: `'Lavoriamo : si
  eme gia da qualche mese'` è diventato `"Us: We've been working together..."`.
  L'errore di lettura diventa una parola nella traduzione.

## Il banco

```powershell
.\.venv\Scripts\python.exe -m tools.selftest                    # 1164 verifiche
.\.venv\Scripts\python.exe -m tools.dub testGameplayFattoDaMe.mp4 --profile gtav `
    --start 1240 --end 1290 --set vision.ocr_backend=oneocr --mp4
.\.venv\Scripts\python.exe -m tools.overlay_mp4 testGameplayFattoDaMe.mp4 runs\<passata> `
    --profile gtav --offset 1240 --frames 4 --out runs\ov\o.png
.\.venv\Scripts\python.exe -m tools.reopen runs\<cartella> [secondo]
```

Dal vivo:

```powershell
powershell -ExecutionPolicy Bypass -File tools\prova.ps1 -Traduci `
    [-Set translate.background_mode=riquadro]
```

## Le lezioni di questa sessione

**Un rimedio che stringe può stringere sul posto sbagliato, e sembra comunque un
progresso.** Il riquadro passava da 1516x391 a 670x108: tutti i numeri
miglioravano. Guardando il fotogramma dipinto, stava **dove il sottotitolo non
c'era** — peggio di prima, che almeno lo copriva. Le misure che guardavo erano
tutte di *quanto*, e lo sbaglio era *dove*. Su una correzione geometrica, la
verifica è l'immagine.

**Controllare che la misura distingua le due risposte.** La prima prova sul blur
del compositore guardava solo l'energia alle alte frequenze — che crolla tanto se
sfochi quanto se copri. Diceva «SFOCA» a due API che non sfocavano.

**Prima di misurare qualcosa, guardare se è già misurato.** `overlay.ritardo`
esisteva e veniva buttato. La domanda dell'utente aveva la risposta già raccolta,
e io l'ho cercata con un banco.

**Quando qualcosa arriva tardi, guardare cosa aspetta, non quanto costa.** Il
ridisegno del blur costa 10,5 ms; il ritardo era gli 84 ms di OCR che aspettava
senza motivo.

Fine del prompt.
