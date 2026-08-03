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
