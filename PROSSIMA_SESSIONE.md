# Prompt per la prossima sessione

Copia da qui in giù.

---

Lavoro su **livedub** (`C:\Users\filde\Documents\!code\CLAUDE\livedub`), doppiaggio
italiano live dei sottotitoli di GTA V. Leggi `CLAUDE.md` e basta: **non leggere
il README per intero**, costa e non serve.

Quello che l'utente vuole, in ordine: **doppiaggio il più live possibile**;
**riconoscimento di chi parla che parte da vuoto e impara ascoltando**, senza
profili preaddestrati; **qualità della voce**.

## Il banco, che è lo strumento di tutto

```powershell
# una volta per registrazione: costa una passata di OCR (~3 minuti)
.\.venv\Scripts\python.exe -m tools.dub testGameplayFattoDaMe.mp4 --profile gtav `
    --start 1240 --end 1340 --set vision.ocr_backend=oneocr `
    --dump-speaker runs\banco\speaker.jsonl

# tutte le altre: 50 millisecondi l'una
.\.venv\Scripts\python.exe -m tools.recluster runs\banco\speaker.jsonl --profile gtav
.\.venv\Scripts\python.exe -m tools.recluster runs\banco\speaker.jsonl --profile gtav --shuffle
.\.venv\Scripts\python.exe -m tools.recluster runs\banco\speaker.jsonl --profile gtav `
    --sweep speaker.merge_similarity 0.50:0.95:0.025
.\.venv\Scripts\python.exe -m tools.reopen runs\<cartella>      # anche sulle prove di dub.py
```

`--shuffle` è **il numero che decide** una soglia: le stesse impronte permutate
fra le battute, dove nessuna identità esiste più. Se una soglia fonde là quanto
qui, non sta fondendo identità.

`tools/dub.py` scrive `events.jsonl` e `config.json` come una sessione dal vivo,
quindi `tools/reopen.py` legge anche le prove sul banco. La politica di
assegnazione delle voci sta in `speak/pool.py` (`voce_per`) e **non** nella
pipeline, proprio perché il banco deve rigiocare quella vera.

## Stato: la scena del concessionario, 44 battute in 100 s, tre uomini

|  | prima di ieri | adesso |
|---|---|---|
| identità con una voce | 4 (di cui una sbagliata) | **3**, quante sono |
| uomini con voce femminile | 1 (quello con più battute) | **0** |
| compressione WSOLA p50 | 1,146 | **1,000** |
| battute compresse al tetto | 25% | **14%** |
| battute «al massimo dell'accelerazione» (`reopen`) | 25% | **0%** |
| latenza percepita p50 | 576 ms | 589 ms (Piper), 752 (SuperTonic) |
| battute che cambiano voce | — | **0** |

SuperTonic adesso gira come Piper: stessa coda, stessa compressione, tre voci
**native** (M1, M2, M3) invece di tre `riccardo` spostati di semitoni. Costa 163
ms di latenza in più. Il default resta `piper` finché non lo giudica l'orecchio:
si prova con `--set tts.backend=supertonic`.

## Le quattro cose trovate stanotte, in ordine di quanto pesano

**1. Il ritardo costante non è un debito di ogni battuta.** Il budget era
`finestra prevista − tempo già passato`, e dentro c'era anche il mezzo secondo di
attesa per sapere chi parla, che torna identico a ogni riga. Chiedere a ognuna di
recuperarlo significa comprimerle tutte per un ritardo che tornerà comunque.
`timing.accepted_delay_ms = 250` è quanto se ne accetta; la tabella che lo sceglie
sta nel docstring di `fuse/timing.py`. La deriva, che era il rischio, non c'è: le
ultime dieci battute sono in ritardo **meno** delle prime dieci.

**2. `chars_per_second` era contato in un'unità e usato in un'altra.** Valeva
17,4 misurato su *tutti* i caratteri, ma viene diviso per `spoken_length()`, che
conta **solo lettere e cifre** — l'81% del testo. Ogni durata prevista era corta
di un quarto. È lo stesso errore di forma preso altre due volte in questo
progetto (selezionare con un operatore e misurare con un altro), travestito da
unità di misura. Adesso il passo lo **dichiara il motore**: Piper 13,7,
SuperTonic 8,6 per unità di velocità (misurato lineare).

**3. L'anello di correzione della velocità inseguiva la propria uscita.** Il
divario era `richiesta / ottenuto`, e `richiesta` è `bersaglio × guadagno`: ogni
volta che la voce restava indietro l'anello alzava sia il guadagno sia il
traguardo. Con il bersaglio a 1,20 consegnava 1,70. Ora il divario si misura
contro `nativo`. **E il bersaglio si calcolava sulla finestra sbagliata**: i due
`plan` della stessa funzione usavano due `elapsed` diversi, e la battuta veniva
accelerata per stare in una finestra più larga di quella in cui poi doveva
stare davvero — il residuo cadeva su WSOLA, cioè sulla leva che schiaccia invece
di articolare.

Questi tre insieme spiegano il tagliuzzato di SuperTonic, e nessuno dei tre era
suo.

**4. Sotto 0,30 di somiglianza non si fa più un nome.** Misurato confrontando la
porta veloce con la porta lenta: sotto quella soglia la veloce prende 2 battute
su 13, sopra 25 su 29. Quelle 13 sono i primi trenta secondi, quando un solo
personaggio è confermato e chiunque parli riceve il suo nome — la partenza lenta.
Adesso lì la decisione è **anonima**: voce neutra, nessuna voce del pool
consumata. **Il prezzo è dichiarato**: delle 18 battute neutre, 15 stanno nei
primi 37 secondi dove il rimedio è giusto, ma **3 sono isolate a metà scena**, e
lì l'orecchio — che ha già imparato le voci — può sentire la neutra come un
quarto personaggio. Va giudicato all'ascolto; si spegne con `--set
speaker.name_min_score=0`.

## La prova del soffitto, e come si e' rovesciata

L'idea era: il parlato stacca dal fondo di pochi decibel, quindi separare la voce
dal fondo dovrebbe alzare il soffitto del riconoscimento. Provata due volte, e
tutte e due le volte la risposta e' stata «il trattamento non e' stato
applicato»:

- **HDEMUCS** (`.venv-f5` di `gta-redub-live`; li' `torchaudio.load` non
  funziona, torchcodec non carica la DLL, si legge il WAV col modulo standard e
  si aggira): correlazione **0,983** fra il centro originale e lo stem «vocals»,
  rms al 96%, e nelle pause del dialogo il separato e' piu' **forte**
  dell'originale. E' addestrato su musica: su dialogo con effetti mette tutto
  dentro «vocals»;
- **sottrazione spettrale** scritta a mano (niente da installare; la STFT e'
  stata verificata contro la propria inversa **prima**, scarto 6e-08):
  correlazione 0,986. Toglie solo rumore stazionario, e qui non ce n'e' molto.

Poi la misura che ha rovesciato la domanda. Se i 190-300 Hz nei ritagli di Lamar
fossero fondo, starebbero **soprattutto nelle finestre deboli**, dove il parlato
non li copre. Misurato sulle sue 1517 finestre sonore, divise per energia:

    quarto piu' debole   intonazione mediana 151 Hz   sopra 190 Hz  34%
    secondo quarto                           180 Hz                 46%
    terzo quarto                             198 Hz                 53%
    quarto piu' forte                        217 Hz                 69%

Correlazione fra energia e intonazione **+0,40**, con la confidenza
dell'autocorrelazione che sale insieme (0,58 -> 0,80). E' il contrario del fondo:
**e' un uomo che alza la voce**, e alzandola sale di intonazione. In quella scena
urla.

Quindi il percentile basso non ripulisce niente: prende il **fondo tonale del
parlatore**, come suona quando non grida — che e' anche il motivo per cui
identifica meglio la persona, perche' quanto uno gridi dipende dalla scena e la
sua voce di base no. La spiegazione sbagliata era rimasta in piedi perche' il
rimedio funzionava: **un rimedio che funziona non conferma la diagnosi.**

Il controllo che rende leggibili queste prove e' `runs/banco_orig.jsonl`: le
stesse impronte ricalcolate sull'audio **originale** con lo stesso script. Non
riproduce esattamente il dump della pipeline (16 identita' invece di 15, perche'
il ritaglio parte da `t_on` e non dall'onset del VAD), ed e' proprio per questo
che serve: l'unica differenza attribuibile e' quella fra i due trattamenti.

## Kokoro-82M, il terzo motore (sessione del 3 agosto 2026)

Aggiunto e misurato, **default ancora `piper`**. Si prova con
`--set tts.backend=kokoro`.

### I numeri, tutti misurati sulla stessa scena e nella stessa sessione

| banco (orologio virtuale) | sintesi p50 | p95 | latenza viva p50 | fretta p50 |
|---|---|---|---|---|
| piper | 45 ms | 80 | **589 ms** | 1,00 |
| supertonic | 210 ms | 284 | **752 ms** | 1,06 |
| kokoro (CUDA) | 299 ms | 601 | **932 ms** | 1,19 |

| `--tempo-reale` | latenza viva p50 | sintesi p50 | frame saltati | battute |
|---|---|---|---|---|
| piper | 1372 ms | 52 ms | 649 | 43 |
| kokoro | **1949 ms** | 281 ms | 883 | 42 |

**La riga che decide il vivo e' la seconda.** 229 ms di sintesi in piu' diventano
577 ms di latenza: il costo si amplifica invece di sommarsi, perche' la sintesi
sta nel thread video. **La prova dal vivo non e' ancora stata fatta.**

Altro di misurato: su CPU Kokoro costa **725 ms** (non vivibile, per questo il
`.venv` monta ora `onnxruntime-gpu`); il quantizzato da 92 MB e' **quattro volte
piu' lento** del fp32; il passo e' **12,9 car/s** in unita' `spoken_length` — piu'
adagio di Piper, per questo la catena gli chiede fretta piu' spesso; il tetto
d'integrita' e' **1,30** contro l'1,10 di SuperTonic, quindi assorbe piu' fretta
articolando; e' **deterministico** campione per campione, l'unico dei tre.

### Le voci italiane sono due, e questo non lo risolve nessun motore

`if_sara` e `im_nicola`. Il pool si riallarga per pitch-shift esattamente come
con Piper: nella scena i tre uomini sono `nicola`, `nicola-2_5`, `nicola+2_5`.
Quindi il salto di qualita' vale sul **primo** personaggio, non sul terzo, ed e'
li' che va giudicato all'ascolto.

### Cosa e' cambiato nel codice, oltre al backend

- **`speak.base.make_tts`**: la costruzione del TTS era ripetuta in sei file e
  ognuno passava parametri diversi. Adesso ce n'e' uno solo, prende la sezione
  intera, e un nome sconosciuto **solleva**. Verificato neutro rigirando Piper
  con e senza le modifiche: identita' identiche al 100%.
- `preload` di Kokoro **sintetizza una volta a vuoto**: senza, la prima battuta
  costava 745 ms invece di 275, perche' su CUDA la prima inferenza compila i
  kernel. Cadeva sulla prima battuta di una partita, la sola che non si recupera.
- `tts.device` (`cpu | cuda | auto`) da oggi **e' letto**, e solo da Kokoro.

### Una cosa trovata per caso, e non e' mia

**HEAD non riproduce piu' le passate archiviate.** `runs\finale_piper` ha 44
battute e 5 identita'; Piper rigirato oggi **su HEAD pulito** ne da' 43 e 4, e i
due concordano al 95,6%. La causa e' l'OCR — `Esteban Jimenez.` contro
`Esteban Jimenez.7`, e una battuta letta come frammento unito invece che
separata — quindi sta a monte del TTS ed e' anteriore a questa sessione. Le
tabelle qui sopra sono tutte rimisurate oggi e fra loro si confrontano; **quelle
piu' in alto in questo file no.**

## La sessione del 3 agosto 2026: quattro esperimenti, quattro no

Nessuno di questi ha prodotto codice. Sono qui perche' **ripeterli costa piu' che
leggerli**, e tre dei quattro erano item scritti in `SviluppoProgetto.md`.

### 1. La sintesi fuori dal thread video — provata dal vivo, non paga

L'idea era buona e il banco la confermava: `on_frame` sta fermo mentre il motore
sintetizza, i frame arretrati si saltano, e il lettore di sottotitoli e'
costruito su frame *consecutivi*. Scritta (un lavoratore solo con coda FIFO,
perche' le battute vanno dette in ordine), suite verde, misurata:

| `--tempo-reale` | sincrona | asincrona |
|---|---|---|
| piper | 1422 ms | **810** (-43%) |
| kokoro | 2098 ms | **1613** (-23%) |
| supertonic | 2414 ms | **1669** (-31%), frame saltati 1056 -> 554 |

**Dal vivo, stessa scena, SuperTonic: 1300 -> 1410 ms.** Niente, anzi un filo
peggio su ogni colonna. Il codice e' stato rimosso; il perche' sta in `CLAUDE.md`
sotto `--tempo-reale`, ed e' la lezione riutilizzabile: quella modalita' addebita
all'orologio del media il tempo speso in `on_frame`, quindi premia due volte
qualunque cambiamento che sposti lavoro fuori di li'.

Il segnale c'era prima della prova e non e' stato ascoltato abbastanza: **Piper
guadagnava di piu' di tutti** avendo 51 ms di sintesi da nascondere contro i 398
di SuperTonic.

### 2. I tag di espressione di SuperTonic — non recitano

Il README promette dieci tag inline (`<laugh>`, `<breath>`, `<sigh>`); la lista
completa non e' pubblicata da nessuna parte e la issue #155 del repo la chiede
senza risposta. Verificato qui:

- i tag **arrivano** al modello (le parentesi sopravvivono a `_preprocess_text`,
  e SuperTonic 3 e' a livello di carattere: `<laugh>` e' una sequenza imparata
  come `<it>...</it>` per la lingua);
- ma **non producono niente**. Su 22 candidati, nessuno si stacca dalla retta che
  prevede la durata dalla sola **ortografia** — `<laugh>` dovrebbe cadere lontano
  da quella retta e ci sta sopra. All'ascolto: «un mezzo sospiro», e 2 impulsi
  contro i 10 della parola «laugh» letta.

**Su Piper e Kokoro sono peggio che inutili: vengono pronunciati.** Il
fonemizzatore di Kokoro rende `<sigh>` come `sˈiɡ` — un personaggio direbbe
«sig» in mezzo all'italiano.

### 3. L'ottimizzazione di SuperTonic — nessun margine

Il profilo per stadio (avvolgendo il `run` delle quattro sessioni ONNX):
`vector_est` e' l'**82%** del costo e cresce linearmente coi passi; vocoder,
codificatore del testo e predittore di durata insieme fanno meno di 100 ms e non
si muovono. Quindi c'e' un bersaglio solo, e tutte le sue leve sono chiuse:

| leva | esito |
|---|---|
| passi di diffusione | **al pavimento**: 2 e 3 giudicati «tagliuzzato, non si capisce niente» |
| thread ORT (`intra`/`inter`) | **rumore**: il -22% era una passata fortunata, la ripetizione da' 451-497 dove aveva dato 398 |
| quantizzazione int8 | **+352%** (629 -> 2845 ms), trattamento verificato applicato |

SuperTonic **resta valido**, ma per un'altra ragione che l'utente ha dichiarato e
che non era scritta: e' l'unico dei tre a girare su CPU, quindi e' il livello
«senza GPU» — Raspberry, portatili, chi non vuole contendere la VRAM al gioco.
Verificato che sia davvero CPU: `DEFAULT_ONNX_PROVIDERS = ["CPUExecutionProvider"]`
e' cablato nel pacchetto, quindi i suoi numeri sono onesti anche in questo venv
che monta `onnxruntime-gpu`.

### 4. La virgola sulle frasi spezzate — non fa quello per cui e' stata scritta

Misurato sulle passate archiviate: **il 12% delle battute e' meta' frase** (45 su
385, tre passate concordi). Ma non e' un difetto dell'OCR — e' GTA V che le mostra
come due sottotitoli successivi perche' l'attore fa una pausa, e **la divisione va
tenuta**: ricucirle costerebbe **1852 ms** di attesa mediana, piu' di tutta la
latenza attuale.

L'ipotesi era che la prima meta' venisse detta con l'intonazione di una frase
finita. Falsa per Kokoro (che il punto non lo aggiunge; SuperTonic si', con
`_add_period_if_needed`). All'ascolto la virgola cambia i **tempi**, non
l'intonazione — e infatti allunga il parlato di 0,23 s riempiendo la pausa. Un
rimedio che produce un'altra percezione da quella per cui e' stato scritto non e'
confermato.

### 5. Il contrasto del ritaglio per l'OCR — la misura isolata mentiva

Il ritaglio che va all'OCR e' `luma * maschera`, incollato al testo: niente
margine, niente normalizzazione, niente ingrandimento. Provate tutte, misurate su
250 ritagli veri col lessico italiano come metro (quante parole lette sono parole
vere — non serve la trascrizione a mano, e i difetti veri di questo OCR sono
non-parole: `Baggiungi`, `Simeolu`, `Jimenez.7`):

    leva                parole   italiane   letture vuote
    niente (oggi)         1235       1096        46
    margine 8 px          1424       1209        14
    ingrandisci x2        1371       1200        15

Sembrava vinta: +113 parole italiane, letture vuote a un terzo, e la leva piu'
semplice faceva quanto qualunque combinazione.

**Sulla catena intera si rovescia.** `vision.ocr.non_italiano` da 16 a **46**,
nessun sottotitolo guadagnato (45 -> 44), e fra le battute doppiate compare
questa:

    'LII, HIQ II UZIV IIG IIG pICSU Ia IHIVWTIUI CIa IIIVG IIV CI vayvS: vUI
     tatuaggio in faccia e tutto il resto?'

Spazzatura **saldata davanti a una frase vera**, che sarebbe finita in bocca al
sintetizzatore. Il margine fa leggere anche le righe che prima tacevano, ma
quelle sono scenario: da sole verrebbero buttate dal filtro della lingua, unite a
una battuta vera lo passano.

**La lezione e' sulla misura, non sulla leva.** Contare le parole italiane su
ritagli isolati misura «legge di piu'», non «legge meglio», e non puo' vedere
cosa succede quando le righe si uniscono. Il codice e' stato tolto. Se qualcuno
ci riprova, il metro giusto e' il **testo delle battute doppiate**, non un
punteggio sui ritagli.

### 6. Chatterbox e Qwen3-TTS sul banco — uno misurato, l'altro bloccato

**Sono gia' installati tutti e due**, nei venv delle cartelle sorelle, coi
modelli gia' in cache (3,0 GB Chatterbox, 2,4 GB Qwen, 5,9 GB la variante ONNX).
L'item costava una sessione e costa una prova. Si usano **senza installare
niente**: leggere e far girare quei venv e' permesso, installarci dentro no.

**Chatterbox multilingua** (`.venv-cbx`, torch 2.6+cu124, CUDA), misurato:

| | |
|---|---|
| sintesi p50 | **3394 ms** (p95 4932) |
| VRAM di picco | 3409 MB |
| passo | 10,9 car/s |
| italiano | c'e' (`'it': 'Italian'`, 23 lingue) |
| emozioni | `exaggeration`, continuo 0..1 — **funziona** |
| voci | clonazione zero-shot da un ritaglio, ~3,3-3,9 s |

**Per il vivo e' fuori portata, e non di poco**: 3,4 s di sola sintesi contro una
latenza totale che oggi sta fra 670 e 1873 ms. Ed e' autoregressivo — campiona
token a ~30/s — quindi non c'e' nessun passo di diffusione da tagliare e il costo
cresce con la lunghezza. Servirebbe un **x13**. Secondo campanello: parecchie
battute escono a **esattamente 5,00 s** con l'avviso `forcing EOS token,
long_tail`, cioe' il modello tira via invece di articolare.

Ma **quello che da' in cambio e' esattamente cio' che manca qui**: emozione
continua e **voci illimitate**. Il limite dichiarato di Kokoro e Piper — due voci
italiane, oltre il secondo personaggio si spostano i semitoni — con la clonazione
smette di esistere. Vale come motore **offline**, non dal vivo.

**Qwen3-TTS: bloccato.** Il `transformers` di `.venv-qwen` non conosce
l'architettura `qwen3_tts`, e aggiornarlo sarebbe installare dentro un venv delle
cartelle sorelle. Serve un venv usa-e-getta proprio (torch+cu128, alcuni GB).
Quello che si e' potuto leggere dall'API e' pero' il pezzo piu' interessante di
tutta la ricognizione:

- **`instruct`**: lo stile chiesto **in linguaggio naturale** («parla con
  rabbia»), non con un tag. E' cio' che i tag di SuperTonic promettevano;
- `generate_voice_clone` e `generate_voice_design`;
- **`non_streaming_mode: bool = True`** — cioe' esiste uno **streaming**. Per
  questa catena e' il parametro che conta piu' della velocita' grezza: con lo
  streaming il numero sul percorso critico e' il **primo campione**, non la
  sintesi intera. E' anche perche' i 3,4 s di Chatterbox sono tutti latenza:
  li' lo streaming non c'e'.

**E c'e' una variante ONNX gia' in cache** (`wavekat/Qwen3-TTS-1.7B-VoiceDesign-ONNX`,
5,9 GB) con `fp32` **e `int4`**, `talker_prefill` e `talker_decode` separati e uno
script `generate_onnx.py`. ONNX e' il runtime che questo progetto usa gia': se
qualcosa di questa famiglia puo' entrare in `speak/backends/`, e' quello.

**Una correzione a `CLAUDE.md`**: la tabella dei venv sorelle da' `.venv-qwen`
per `torch 2.11.0+cpu`, «no torch CUDA». Oggi ha **2.11.0+cu128 con CUDA
disponibile**. Il venv e' stato aggiornato dopo quella nota.

## Lo stato di `SviluppoProgetto.md`

| item | stato |
|---|---|
| voci femminili agli speaker | **risposto**: si', con ripiego maschile dichiarato (`speaker.gender_fallback`). Il lavoro vero resta: la taratura del genere non e' mai stata provata su una donna, perche' nella registrazione non ce n'e' una |
| speed regolato dal vivo | **gia' implementato**, e fa tutte e tre le cose chieste: una voce alla volta, stringe in volo il residuo quando arriva il sottotitolo dopo (`hurry_on_next`), e il ritardo accumulato entra nel budget della battuta successiva |
| tag di espressione | **chiuso**, negativo (§2) |
| ottimizzazione di SuperTonic | **chiuso**, nessun margine (§3) |
| frasi lunghe su due righe | **chiuso**: il 12% e' meta' frase, ma la divisione va tenuta e la virgola non cura (§4) |
| contrasto per l'OCR | **chiuso**, negativo (§5) |
| SuperTonic su PC vecchi | **non provabile qui**: serve l'altro PC |
| controllo di grammatica sul testo | **risposto**: c'e' un filtro di lingua (`vision/lexicon.py`), e correggere e' stato provato e **rifiutato di proposito** — 2 giuste su 8, e gli errori erano `rapinato` -> `rovinato` |
| parola colorata -> non leggere la frase | **gia' fatto**: `sat_ink_max` la prende. L'obiettivo `Raggiungi Vespucci Beach.` viene scartato perche' il ciano e' il 44% del suo inchiostro. Aggiunto `vision.lines.mixed_ink` per vedere il caso che sfuggirebbe (parola colorata **corta** in una frase lunga), che su questa scena non capita |
| LLM leggero per gli artefatti OCR | **aperto**. Ma leggere prima il docstring di `vision/lexicon.py`: la correzione automatica e' gia' stata bocciata li', e un LLM sbaglia nello stesso modo, meglio e quindi piu' pericolosamente. Ha senso solo se **dichiara quando non e' sicuro** |
| traduzione + riquadro grafico | **aperto**, ed e' il piu' grande |
| Qwen TTS e Chatterbox sul banco | **Chatterbox misurato** (§6): 3394 ms a battuta, fuori portata dal vivo, ma da' emozione continua e voci illimitate — vale come motore offline. **Qwen bloccato** su un `transformers` vecchio in un venv che non si tocca; la sua variante **ONNX con int4 e streaming** e' la pista giusta per questa catena |
| nome del parlante scritto dal gioco | **aperto**, e vale la latenza: toglierebbe i 500 ms di `decide_after_ms`, che oggi costano **il doppio della sintesi**. Non misurabile su questa registrazione — GTA V i nomi non li scrive |

**Una cosa trovata di striscio e non in lista**: nella sessione dal vivo, **37
battute su 108** sono state dette con la voce neutra, cioe' un terzo della scena
detto da «non so ancora chi sia». E' tanto e nessuno lo stava guardando.

## Cosa resta aperto, in ordine

0. **L'ascolto di Kokoro, e poi il vivo.** `runs\finale_kokoro\dub.mp4` è la
   scena intera con il testo dell'OCR a schermo. Le domande: l'italiano **è**
   italiano (le voci sono state addestrate soprattutto sull'inglese, e a monte
   segnalano prosodia anglicizzata)? I 932 ms contro i 589 di Piper si sentono?
   I due timbri reggono spostati di ±2,5 semitoni per fare tre uomini?
   Se l'orecchio approva, il vivo è
   `-m tools.ui --profile live --loopback voicemeeter --set vision.ocr_backend=oneocr --set tts.backend=kokoro`,
   **ma la passata `--tempo-reale` dice di aspettarsi peggio del banco**: 1949 ms
   contro 1372 di Piper. Se il difetto delle battute non lette ricompare, è una
   previsione confermata, non una sorpresa.

1. **L'ascolto.** Tutto quello che sta qui sopra è misurato ma non ascoltato.
   `runs\finale_piper\dub.wav` e `runs\finale_supertonic\dub.wav` sono la stessa
   scena con i due motori. Le domande da fare all'orecchio: SuperTonic articola
   le battute intere adesso? La voce neutra a metà scena dà fastidio? I 752 ms di
   SuperTonic si sentono contro i 589 di Piper?
2. **Una prova dal vivo**, che è un'altra cosa dal banco: `tools/ui.py`, video di
   GTA V in Chrome a schermo intero, VoiceMeeter, cuffie.
3. **La pulizia del segnale non e' piu' la prima candidata.** L'unica prova che
   la sosteneva era l'intonazione di Lamar, ed era la sua voce. Resta possibile
   che aiuti l'impronta di speaker — quella e' un'altra domanda, e per porla
   serve un modello di *speech enhancement* (DTLN, RNNoise, la variante `dns48`
   di Demucs), non un separatore musicale. Ma prima conviene chiedersi se il
   riconoscimento sbagli ancora abbastanza da giustificarlo.
4. **La scena fitta.** La deriva della coda è stata misurata su una scena dove
   l'italiano occupa il 65% del tempo. Su una più fitta va riguardata: è la
   prima cosa da rimisurare se il doppiaggio comincia a slittare.
5. Le voci femminili: la taratura del genere non è calibrata su una donna, perché
   in questa registrazione non ce n'è.

## Comandi

```powershell
.\.venv\Scripts\python.exe -m tools.selftest                 # 812 verifiche
.\.venv\Scripts\python.exe -m tools.ui --profile live --loopback voicemeeter --set vision.ocr_backend=oneocr
.\.venv\Scripts\python.exe -m tools.dub testGameplayFattoDaMe.mp4 --profile gtav --start 1240 --end 1340 --mp4 --set vision.ocr_backend=oneocr
.\.venv\Scripts\python.exe -m tools.bench_speaker --clean
```

**Il rettangolo disegnato a mano è il percorso di produzione** — l'utente finale
farà così — quindi non si torna ai profili calibrati per far tornare i conti.

`tools/dub.py` verifica da solo che l'uscita **differisca** dall'audio di
ingresso, perché una volta produceva un file identico all'originale mentre i log
dicevano 46 battute doppiate.

Non toccare i 500 ms di attesa senza rimisurare: la tabella è in
`SpeakerConfig.decide_after_ms`. È già stato provato a toglierli per curare
SuperTonic, e non era quella la cura — la latenza peggiora, p50 789 ms e p95
3025, perché la coda si accumula.

## Le lezioni di metodo, che valgono più del codice

**Due errori che si compensano sono più pericolosi di un errore solo.** La stima
delle durate era corta di un quarto e l'anello di correzione la compensava
alzando il guadagno: il risultato finale era ragionevole, e infatti nessuno se
n'era accorto in mesi di ascolto. Correggendo *solo* la stima, tutto è
peggiorato di colpo — 89% delle battute al tetto. Quando una correzione giusta
peggiora le cose, il difetto non era uno.

**Il caso nullo migliore condivide tutto tranne la risposta.** Le impronte
permutate fra le battute lasciano identiche scena, tempi e alternanza, e tolgono
solo *chi è chi*: sono loro ad aver fissato la soglia della fusione a 0,70, dove
il conteggio delle identità da solo avrebbe scelto 0,50.

**Verificare che il trattamento sia stato applicato, prima di leggere il
risultato.** La prova del separatore vocale dava un risultato pulito e falso: il
raggruppamento non migliorava perché l'audio non era cambiato. Bastavano una
correlazione e un istogramma per accorgersene, ed erano tre righe.

**Un rimedio che funziona non conferma la diagnosi.** Il percentile basso sulla
f0 curava il difetto, quindi la spiegazione che lo accompagnava — «c'è del fondo
tonale che contamina la stima» — è rimasta in piedi senza essere verificata. Era
sbagliata: quelle frequenze sono la voce di un uomo che urla, e si vede perché
salgono con l'energia della finestra invece di stare nelle pause. La conseguenza
non è cosmetica: sulla diagnosi sbagliata avevo scritto in cima alle cose da
fare «pulire il segnale», che è una sessione di lavoro.

**Un'unità di misura è un operatore come un altro.** «17,4 caratteri al secondo»
era vero, ma di un'altra definizione di carattere rispetto a quella usata per
dividere. Nessuna verifica poteva prenderlo, perché entrambi i numeri erano
giusti — sbagliato era il fatto che si incontrassero.

**E la più importante: l'orecchio dell'utente trova ciò che la suite non può.**
Anche stanotte: 812 verifiche verdi mentre SuperTonic era inascoltabile. Quando
l'utente dice «non funziona» e i numeri dicono di sì, **sono i numeri a essere
sotto esame**.

---

Fine del prompt.
