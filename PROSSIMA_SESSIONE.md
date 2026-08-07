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

Suite verde a **1172 verifiche**. La sessione del 7 agosto ha chiuso quattro
difetti e ne ha *smentito* un quinto con una misura. Tutti e quattro sono stati
trovati guardando **il video della sessione dell'utente e il suo log a schermo**,
non i contatori: nessuno dei quattro faceva scattare un numero.

Il riferimento è `runs/2026-08-07_01-40-16` (589 battute, 45 minuti dal vivo).

## Il banco nuovo, che cambia il modo di lavorare

`yt_scena.mp4` (282 MB, gitignorato) è la scena della sessione dell'utente
scaricata da YouTube a 1080p60. **Il video è avanti di 29,5 s rispetto ai tempi
della sessione dal vivo** (il primo pezzo è il riassunto dell'episodio prima).

```powershell
.\.venv\Scripts\python.exe -m tools.dub yt_scena.mp4 --profile gtav --start 29 --end 315 `
    --set vision.ocr_backend=oneocr
```

Riproduce il tetto di compressione e la frammentazione delle identità con la
stessa forma del vivo. Prima serviva una sessione intera dell'utente per provare
una modifica sul riconoscimento; adesso sono tre minuti. Se serve un'altra scena,
si scarica con `yt-dlp` installato **fuori dal venv** (`pip install --target`) e
`--download-sections`.

## Le quattro cose corrette

**1. La voce restava neutra su tutto, e la causa era un ramo che non attaccava
niente.** A pool pieno (`max_speakers = 16`) `impara` restituiva l'id del
migliore senza contargli la battuta. Il pool si riempie con le prime 16 righe,
quindi da lì in poi *ogni* riga passava di lì: nessuno arrivava a due battute,
nessuno diventava `confermato`, e `scegli` — che sceglie solo fra i confermati —
restituiva zero per sempre.

Dal vivo: voci neutre da **98/101 (97%) a 208/589 (35%)**, punteggio p50 da 0,136
a **0,394**, `battute_note` p50 da 0 a **52**, tre voci vere in uso.

**2. Il bordo sfumato della toppa rimetteva il sottotitolo da nascondere.** La
sfumatura mescolava lo sfocato con i pixel del gioco: sul bordo ricompariva
l'italiano. Misurato, l'inchiostro originale si leggeva il **doppio** sulla
cornice che al centro (68,3 contro 34,2). Spenta (`sfuma = 0`).

**3. La parola colorata: il criterio non poteva scattare.** `_corsa_piu_lunga`
girava sulle colonne grezze e fra le lettere c'è del vuoto, quindi misurava **la
lettera più larga**: quota 0,043 contro una soglia di 0,15. Adesso le lettere si
saldano prima (`_chiudi_buchi`, `color_word_gap = 0.28`, misurato: 0,16-0,205 fra
lettere e 0,375-0,438 fra parole).

**4. L'HUD sulla stessa riga finiva nel ritaglio e veniva pronunciato.** Il
ritaglio andava dalla prima all'ultima colonna d'inchiostro: nome della strada,
radio, nomi di app. Nella sessione dell'utente **63 battute su 576, l'11%** —
`.San An`, `.Las Laguni`, `SiniQuelli erano...`. Adesso la banda si spezza ai
buchi larghi (`line_gap_split = 2.5`, sei volte uno spazio) e si tiene il blocco
**più vicino al centro**, perché GTA V centra i sottotitoli e mette l'HUD ai bordi.

## L'ipotesi smentita, e vale quanto le correzioni

`dub.rate_x1000` sta al tetto sul 20% delle battute. L'ipotesi era: la finestra è
prevista corta, quindi si comprime per niente.

Per rispondere ho dovuto **rendere la domanda rispondibile**: la durata vera del
sottotitolo veniva osservata da `timing.observe` a ogni riga e buttata via.
Adesso finisce nel registro come `kind: "finestra"` (con la previsione presa
*prima* che il modello impari da lei). Misurato, sulle battute al tetto:

| | |
|---|---|
| finestra prevista | 1,37 s |
| finestra **vera** | **0,93 s** |
| durata naturale del parlato | 1,25 s |
| entrerebbero senza comprimere | **4 su 17 (24%)** |

**L'opposto dell'ipotesi**: la previsione era già generosa e la compressione è
necessaria in tre casi su quattro. Nel predittore non c'è niente da correggere.

## La decisione aperta, ed è dell'orecchio dell'utente

**`tts.native_rate_max` vale 1,55 ed è un numero solo per tutti i motori.** I
tetti di integrità misurati e scritti in `CLAUDE.md` sono **1,10 per SuperTonic e
1,30 per Kokoro**. Con Kokoro la catena spinge il motore venticinque centesimi
oltre il punto dove è stato misurato che la voce regge, e passa il residuo a
WSOLA, che si inchioda al suo 1,25.

È la stessa forma di errore già pagata due volte con `chars_per_second`, e sta
scritta nel file stesso: *«ogni backend dichiara il proprio passo e il proprio
tetto: un numero solo per tutti i motori è già costato due sessioni»*.
`chars_per_second` è stato reso per-backend; `native_rate_max` no.

**Non è un guadagno gratis.** Abbassarlo a 1,30 fa articolare meglio il motore e
sposta *più* carico su WSOLA, che schiaccia peggio. Alzare `timing.rate_max` sopra
1,25 fa sparire le consonanti. I due si scambiano il difetto, e quale si senta
meno lo decide l'orecchio. **Il modo di chiederglielo è pronto e non richiede il
gioco acceso**: due MP4 della stessa scena con `tools/dub.py --mp4`, uno a 1,55
nativo e uno a 1,30, ascoltati affiancati. Mezz'ora di banco. Non è stato fatto.

## Quello che resta, in ordine di quanto costa

- **L'area di cattura dell'utente era alta 0,144**, sopra la soglia di 0,12 su cui
  la UI avvisa. Misurato: con un'area così il banco legge **50 battute invece di
  115**. Un'area larga non fa solo entrare l'HUD, fa leggere peggio. È il singolo
  cambiamento col rapporto migliore fra sforzo e risultato, e lo fa l'utente.
- **`speaker.ring_lag` mente.** Dice 5543 ms mentre `ritardo_anello` per battuta
  dice 7 ms. Ha mandato una diagnosi fuori strada per mezza sessione, e sta nel
  report che si legge all'inizio della prossima. Va aggiustato o tolto.
- **Il riquadro sfocato ogni tanto va a 1318×154 o 175**, contro i 48-107 normali.
  È la saldatura con lo sfondo chiaro, e discende dall'area larga: stringendola
  dovrebbe sparire da sola. Da riverificare **dopo** che l'area è stretta.
- Il caso della parola colorata **corta** in una frase lunga («Premi **E** per
  entrare») resta scoperto: quota 0,025, sotto qualunque soglia che non butti via
  dialogo.
- La verifica di `line_gap_split` **sull'area larga** non è stata portata a
  termine (passata in timeout). L'11% è la misura del difetto, non del rimedio.

## Il banco

```powershell
.\.venv\Scripts\python.exe -m tools.selftest                    # 1172 verifiche
.\.venv\Scripts\python.exe -m tools.dub yt_scena.mp4 --profile gtav `
    --start 29 --end 315 --set vision.ocr_backend=oneocr --mp4
.\.venv\Scripts\python.exe -m tools.reopen runs\<cartella> [secondo]
.\.venv\Scripts\python.exe -m tools.recluster runs\<cartella>\speaker.jsonl --profile gtav
```

Dal vivo:

```powershell
powershell -ExecutionPolicy Bypass -File tools\prova.ps1 -Traduci -Traduttore google `
    [-Set translate.blur_strength=45]
```

## Le lezioni di questa sessione

**Uno spazzamento piatto non sta misurando la soglia che spazza.**
`merge_similarity` da 0,35 a 0,90 non muoveva **un solo numero**: 16 identità con
una battuta sola a ogni valore. Quello non è "la soglia è sbagliata", è "la
variabile è un'altra e sta a monte". È il segnale che ha portato al difetto vero.

**Il pezzo si prova fuori dalla catena.** La banca alimentata a mano con le
impronte già registrate ha separato in un minuto «la banca sbaglia» da «la catena
non la usa come crede». Nella catena i due sono indistinguibili.

**Una verifica può esistere a metà.** Quella sul tetto del pool controllava che il
pool non si superasse, non che il ramo facesse il suo lavoro. Era verde mentre il
difetto rendeva neutra ogni voce della sessione.

**Il primo censimento era mal posto e diceva il contrario.** Calcolavo la
saturazione con HSV invece che con `luma_sat()` del progetto: sulla sabbia l'HSV è
saturo dappertutto, e la misura dichiarava «perdi il 33% del dialogo» su una
correzione che non ne perde niente. Prima di credere a un numero, controllare che
usi le definizioni della catena e non delle proprie.

**Il surrogato ha colpito ancora.** Per tarare il taglio dell'HUD ho costruito i
ritagli a mano e dati all'OCR: spazzatura **anche a trattamento spento**, quindi
la misura non poteva esprimere niente. La risposta è venuta facendo girare la
catena vera due volte.

**Rendere la domanda rispondibile è metà del lavoro.** La durata vera del
sottotitolo passava per `timing.observe` a ogni riga da sempre. Registrarla ha
richiesto sei righe e ha ucciso un'ipotesi su cui si sarebbe potuta spendere una
sessione intera. È il sesto campo misurabile e mai letto di questo progetto, dopo
`overlay.ritardo`, `max_ocr_hz`, `tts.device` e `background_mode`.

**Il log a schermo dell'utente vale quanto la sua registrazione.** I frammenti di
HUD incollati alle battute — il difetto più grosso rimasto — si leggevano nella
finestra di livedub dentro il suo video. Nessun contatore li mostrava, perché per
la catena erano righe lette con successo.

Fine del prompt.
