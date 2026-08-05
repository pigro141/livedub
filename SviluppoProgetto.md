# live dub tts

## Dove siamo

**Feature: 14 su 14.** Tutte chiuse, comprese quelle che si sono chiuse con un
"no" misurato (i tag del TTS, la correzione automatica per distanza di edit, Qwen).

**Step finali: 2 su 17.** Le due spuntate — colore/dimensione dei sottotitoli e
scelta delle lingue — sono fatte **come meccanismo**: i parametri esistono e si
regolano da `--set`. Quello che manca è la UI che li espone.

I quindici rimasti sono tre blocchi, e il primo blocca gli altri:

| blocco | cosa | quanti |
|---|---|---|
| **UI** | interfaccia, selettore tecnologie, impostazioni avanzate con spiegazioni, modifica a caldo | 4 |
| *(cancello)* | **la tua prova, con report di cosa va e cosa no** | — |
| **distribuzione** | installabile, exe, licenza | 3 |
| **repo** | il repo più i suoi sette punti | 8 |

**Nessuno aspetta una misura.** L'unico che poggiava su dati — i requisiti minimi
— ce li ha già tutti. Da qui in poi è lavoro di interfaccia e di confezione, non
di misura: il contrario di tutto quello che è venuto prima.

*(La riga per riga sta sotto: ogni voce fatta porta il suo esito, comprese quelle
che si sono chiuse con un "no".)*

* **Cosa ho fatto**

  1. riconoscimento testo con ocr
  2. lettura live del testo
  3. riconoscimento speaker differenti
  4. attribuzione di voce diversa in base allo speaker
* **Feature**

  * \[x]  capire se associa potenzialmente voci femminili agli speaker
    → **sì**, con ripiego maschile dichiarato (`speaker.gender_fallback`): l'intonazione
    presa sul mix del gioco sa dire "uomo" meglio di "donna". **Resta**: la taratura del
    genere non è mai stata provata su una donna, nella registrazione non ce n'è.
  * \[x]  capire se il tts una volta generato viene applicato uno speed regolato live …
    → **già implementato**, e fa tutte e tre le cose chieste: una voce alla volta; se
    appare un altro sottotitolo stringe **in volo** il residuo non ancora suonato
    (`hurry_on_next`); il ritardo accumulato entra nel budget della battuta dopo.
  * \[x]  utilizzo dei tag nella generazione audio (`<laugh>`, `<breath>`, `<sigh>`)
    → **non funzionano**. Arrivano al modello, ma nessuno dei 22 candidati si stacca
    dalla retta che prevede la durata dalla sola ortografia; all'ascolto `<laugh>` è
    «un mezzo sospiro». La lista dei dieci non è pubblicata (issue #155, senza risposta).
    **Su Piper e Kokoro sono peggio che inutili: vengono pronunciati** (`<sigh>` → `sˈiɡ`).
  * \[x]  ottimizzazione estrema del tempo di generazione audio con supertonic
    → **nessun margine**. `vector_est` è l'82% del costo; i passi sono al pavimento (2 e 3
    inascoltabili), i thread ORT sono rumore, int8 costa **+352%**. SuperTonic resta
    valido per un'altra ragione: è **l'unico su CPU**, cioè il livello senza GPU.
  * \[x]  miglioramento su frasi lunghe su due righe
    → **il 12% delle battute è metà frase**, ma la divisione va tenuta: è GTA V che le
    mostra come due sottotitoli perché l'attore fa una pausa, e ricucirle costerebbe
    **1852 ms** di attesa mediana, più di tutta la latenza.
  * \[x]  provare a migliorare la lettura dei sottotitoli modificando il contrasto
    → margine, normalizzazione, binarizzazione, ingrandimento, inversione: **tutte
    negative**, fanno leggere *di più* non *meglio*. Il miglioramento è poi arrivato
    dalla parola colorata (ultima voce).
  * \[x]  capire se il programma con Supertonic rallenta su pc vecchi
    → **sì, e parecchio — misurato qui**, senza l'altro PC. Un PC vecchio è due cose
    insieme (meno core, core più lenti) e la prima si simula con l'affinità del
    processo (`tools/bench_cpu.py`, un processo per punto perché ORT dimensiona i
    thread alla creazione della sessione). Costo della sintesi per battuta:

    | core fisici | supertonic | piper |
    |---|---|---|
    | 8 (questa macchina) | 493-573 ms | ~48 ms |
    | 6 | 946 ms (1,65×) | 109 ms (2,25×) |
    | 4 | **1315 ms (2,30×)** | 261 ms (5,40×) |
    | 2 | 3627 ms (6,33×) | 491 ms (10,2×) |

    → **Su un quattro core SuperTonic non è utilizzabile**: 1,3 s a battuta, e la sintesi
    sta nel thread video dove il costo si amplifica invece di sommarsi. Piper a 261 ms
    regge. **E il numero è un limite inferiore**: l'affinità simula il *numero* dei core,
    non la loro lentezza, quindi un PC vero sta peggio.
    → Il passo (`car/s`) resta 14,5 a ogni livello: cambia il costo, non l'uscita.
    → **Consiglio operativo**: sotto i 6 core, `tts.backend=piper`.
  * \[x]  chiedere se sul testo viene fatto un controllo di grammatica
    → **sì**, filtro di lingua (`vision/lexicon.py`). **Correggere è stato provato e
    rifiutato di proposito**: 2 giuste su 8, e gli errori erano `rapinato` → `rovinato`.
  * \[x]  implementazione di un llm leggerissimo per rimuovere artefatti OCR
    → **fatto, con lo stesso modello che traduce** (`correct.backend=ollama`), e lasciato
    **opzionale e spento**. Misurato su otto casi veri presi dalle sessioni archiviate:

    | correttore | giuste | p50 |
    |---|---|---|
    | **translategemma:4b** | **5/8** | 1784 ms |
    | translategemma:12b | 5/8 | 2451 ms |
    | gemma-3-1b (in-process) | 1/8 | 1892 ms |

    → Il 12b non aggiunge niente e costa il 40% in più: si resta sul 4b. Un solo modello
    caricato serve traduzione e correzione insieme.
    → **Ma 1784 ms per parola sono tanti** e la correzione sta sul thread video, dove il
    costo si amplifica: buono per il banco (`tools/dub.py`), da lasciare spento dal vivo.
    → Le guardie restano tutte: una parola italiana non gli viene **nemmeno mostrata**,
    i nomi propri nemmeno, la proposta deve essere una parola del lessico e vicina, e si
    sceglie **fra candidati** invece di generare — così non può inventare una non-parola.
  * \[x]  implementazione di traduzione con sostituzione grafica
    → **fatta** (`translate/`, sezione `translate` di config, spenta di default: su GTA V
    si tradurrebbe l'italiano in italiano).
    → **Quattro strade a scelta**: `locale` (Argos, leggero, offline), `llm`
    (Gemma 3 1B in-process su CPU), `ollama` (parla in HTTP con Ollama: TranslateGemma
    4b/12b/27b senza toccare il venv) e `google` (**manda ogni sottotitolo a Google**, e
    lo dichiara su stderr). Più `prova`, finto, per il banco.
    → **E su questo materiale la domanda che viene prima della qualità è un'altra: il
    modello dice quello che c'è scritto?** I sottotitoli di GTA V sono pieni di
    parolacce, e un modello che le ammorbidisce consegna un doppiaggio che dice un'altra
    cosa — senza che nessun contatore lo mostri, perché la traduzione riesce benissimo.
    Misurato su sei battute volgari (`tools/bench_translate.py --parolacce`), quante
    hanno tenuto il registro:

    | traduttore | registro tenuto | p50 | dove |
    |---|---|---|---|
    | **google** | **6/6** | **64 ms** | rete |
    | translategemma:4b + `preserve_register` | 2-3/6 | 643 ms | locale |
    | translategemma:4b, template puro | **0/6** | 621 ms | locale |
    | translategemma:12b, template puro | **0/6** | 1734 ms | locale |
    | gemma-3-1b (llama.cpp) | 1/6 | 418 ms | locale |

    → **Il 12b non fa meglio del 4b**: è allineamento, non capacità, quindi il 27b da
    17 GB non cambierebbe la risposta e non l'ho scaricato. TranslateGemma non rifiuta —
    **riscrive in silenzio**: «Get the fuck out of my car, asshole» → «Esci
    immediatamente dalla mia macchina, idiota», e perfino «idiots» → «persone poco
    esperte».
    → **`translate.preserve_register`** sostituisce la frase del template sulle «cultural
    sensitivities» con una che chiede di non ammorbidire: da 0/6 a 2-3/6. Acceso di
    default, perché il materiale è quello che è.
    → **Il template di TranslateGemma va rispettato alla lettera**, due righe vuote
    comprese: sbagliarlo non dà errore, dà una traduzione peggiore, e si finirebbe per
    incolpare il modello.
    → **E il «secondo» di Google non era di Google: era mio.** Aprivo una connessione
    HTTPS nuova a ogni battuta. Separando la preparazione dalla domanda: connessione
    nuova ogni volta **337 ms** p50 (fra 107 e 1095, instabile), connessione tenuta
    aperta **64 ms** (fra 42 e 91, stabile), stretta di mano 94 ms una volta sola. Un
    numero stava per essere archiviato come proprietà del servizio.
    → **L'ordine conta**: si traduce **prima** di stimare i tempi. `chars_per_second` e
    `D = a + b*n` sono misurati sull'italiano e vanno applicati al testo che verrà
    *detto*: «I've never had a black son» sta in 26 caratteri, la traduzione in 30.
    → **Non si resta mai muti**: se la traduzione fallisce o va in eccezione si tiene
    l'originale e si conta. Cache per battuta, perché sta sulla strada critica.
    → **Sostituzione grafica** con tre modi di sfondo (`translate.background_mode`):
    `riquadro` (rettangolo pieno), **`blur`** (si sfoca la ROI: l'originale diventa
    illeggibile ma il gioco resta visibile sotto — molto meno invadente) e `nessuno`.
    Il riquadro si posiziona **dalla ROI del profilo**, cioè dallo stesso rettangolo da
    cui l'OCR ha letto: copre per costruzione quello che c'era.
    → **La sfocatura vale solo mentre un tradotto è a schermo** e gli intervalli attaccati
    si fondono, se no sfarfalla. Verificato che il trattamento sia applicato davvero:
    nitidezza della ROI a **0,00** dentro gli intervalli e **1,00** fuori.
  * \[x]  installare qwen tts e Chatterbox, provare sul banco e stimare l'hardware
    → **fatti tutti e due**, erano già installati nei venv delle cartelle sorelle.
    **Chatterbox**: 3394 ms a battuta su CUDA — fuori portata dal vivo, ma dà emozione
    continua e clonazione zero-shot. **Qwen3-TTS ONNX**: provato a fondo — voci come
    **descrizioni** (pool illimitato), italiano nativo, streaming funzionante — e poi
    **tolto** dopo la prova dal vivo. La voce alla riga sotto dice perché.
  * \[x]  streaming di Qwen3-TTS — **fatto, misurato, e Qwen è stato tolto**
    → Lo streaming funzionava: primo campione a **257 ms** invece di 4820, blocchi
    concatenati identici alla battuta intera, zero underrun sul banco.
    → **Dal vivo no.** Tre soglie dichiarate *prima* della prova, tutte e tre sfondate:
    `mix.underrun` 0 → **5415**; latenza < 2,5 s → **26,7 s** al primo campione;
    compressione < 1450 → **1450 a ogni percentile**. Su 65 battute lette, **25 hanno
    prodotto audio**: quaranta non hanno mai parlato.
    → **E non è l'hardware.** La coda si comprerebbe con una scheda da ~670 GB/s. Ma la
    compressione al tetto su *ogni* battuta non dipende dalla GPU: dipende dal fatto che
    il motore parla **la metà** di Piper (8,4 car/s contro 18,3) e produce il 157% del
    parlato che la scena ha tempo di contenere. Su una 4090 sarebbe identico, solo
    puntuale.
    → **Cosa resta**: il protocollo di streaming (`speak/base.py`), il mixer che tiene una
    battuta **aperta** col suo cuscino (`mix.prebuffer_ms`), la catena che programma prima
    di avere l'audio, e la verifica `streaming` su un motore finto. Il prossimo motore
    autoregressivo eredita tutto.
    → **La lezione**: la domanda decisiva non era la latenza, era **quanto parlato produce
    per secondo di scena**. Si misura sul banco in un minuto.
  * \[x]  adattamento speaker per tutti i giochi (nome del parlante scritto a schermo)
    → **fatto** (`vision/label.py`, sezione `label` di config, spento di default). Quando
    il gioco dichiara chi parla, cadono **tutti e due** i costi: l'attesa di
    `speaker.decide_after_ms` (500 ms, oggi il doppio della sintesi) e il calcolo
    dell'impronta. Il nome viene **tolto** da ciò che si pronuncia.
    → **Modulare, come chiesto**: tre forme pronte (`nome:`, `[nome]`, `nome-`) più una
    regex libera; in alternativa **un colore per personaggio**, con soglia oltre la quale
    non si decide. Per il colore `vision/lines.py` adesso porta fuori il colore medio
    dell'inchiostro: luminanza e saturazione da sole non bastavano.
    → **L'elenco dei personaggi è la guardia forte** (`label.names`): con quello, un OCR
    che legge `Si, era lui` come nome viene scartato invece di diventare un personaggio —
    e ogni falso positivo brucia una voce del pool a chi parla davvero.
    → **Provato solo su testo sintetico**: GTA V i nomi non li scrive. Il contatore
    `vision.label.hit` dice se il formato dichiarato è quello giusto.
  * \[x]  adattamento per gtaV se il sottotitolo contiene una parola colorata
    → **fatto e acceso** (`vision.min_color_word_frac = 0.15`). Il difetto vero non era la
    frase saltata, era **la frase sporcata**: frammenti di HUD colorata incollati dentro il
    sottotitolo e pronunciati (`'Rec.Lavoriamo insieme...'`, `"Sì, era lui.Adam'a App"`).
    Dal vivo: **69 battute contro 66, neutre 14 contro 18**, e l'OCR legge meglio anche il
    resto (`': olta'` → `'svolta'`).
* **Step finali**

  * \[ ]  UI interfaccia chiara e funzionale
  * \[x]  possibilità di modificare i sottotitoli tradotti colore dimensione
    → `translate.color`, `background`, `background_opacity`, `background_mode`,
    `blur_strength`, `font`, `font_frac`, `outline`. La dimensione è una **frazione**
    dell'altezza del fotogramma e non punti: così la stessa configurazione vale a 1080p
    e a 1440p. **Manca la UI che li espone**, non i parametri.
  * \[x]  scegliere lingua input lingua output
    → `translate.source` / `translate.target`. `auto` lo capisce solo Google: i modelli
    offline sono **di** una coppia di lingue, quindi con `locale` un `auto` diventa `en`
    e viene detto, invece di esserlo in silenzio. **Manca la UI**, non il meccanismo.
  * \[ ]  selettore delle tecnologie da usare
  * \[ ]  impostazioni avanzate con regolazione di tutti i parametri con vicino un icona a ogni settings che spiega bene cosa fa e cosa succede se viene cambiato rischi ecc (davvero tuti anche la regolazione delle frequenze maschio femmina)
  * \[ ] cambiamento live dei settings e applicazione live
  * \[ ] selettore aree multiple di traduzioni solo testo e poi quella testo e audio, (attenzione se le aree si sovrappongono non lavorare due volte in quel punto)
  * PRIMA DI INIZIARE LA FASE SEGUENTE FAMMI FARE UNA PROVA e ti faccio un report dettagliato di cosa va e cosa no
  * \[ ]  rendere il tutto facilmente installabile plug and play
  * \[ ]  fare exe
  * \[ ]  scegliere la licenza copyright da usare in base alle librerie e la mia scelta
  * \[ ]  repo github senza collaboratore claude

    * \[ ]  repo professionale dove spiega tutte le feature e lingue supportate
    * \[ ]  spiegazione con un diagramma di flusso di cosa avviene nel programma
    * \[ ]  valorizzazione dell'uso completamente locale ed estrema privacy
    * \[ ]  scrivere requisiti minimi richiesti, e quelli per la migliore esperienza in assoluto
      → **i numeri ci sono già, manca scriverli**: senza GPU si gira con Piper o SuperTonic
      (CPU, e sotto i 6 core **solo** Piper); Kokoro vuole CUDA e 1128 MB di VRAM. È
      l'unico punto degli step finali che poggia su misure, e le misure sono fatte.
    * \[ ]  fare anche un link paypal o qualcosa del genere per prendere delle donazioni
    * \[ ]  fare sito github dove c'è spiegato tutto
    * \[ ]  fruttare hype di gtavi per dire che è compatibile anche con quello
