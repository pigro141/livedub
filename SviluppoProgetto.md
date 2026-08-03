# live dub tts

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
  * \[ ]  capire se il programma con Supertonic rallenta su pc vecchi
    → **non provabile qui**, serve l'altro PC. Quasi certamente non è un bug: la sintesi
    sta nel thread video, dove il costo si amplifica invece di sommarsi.
  * \[x]  chiedere se sul testo viene fatto un controllo di grammatica
    → **sì**, filtro di lingua (`vision/lexicon.py`). **Correggere è stato provato e
    rifiutato di proposito**: 2 giuste su 8, e gli errori erano `rapinato` → `rovinato`.
  * \[ ]  implementazione di un llm leggerissimo per rimuovere artefatti OCR
    → leggere prima il docstring di `vision/lexicon.py`: un LLM sbaglia nello stesso modo
    della correzione già bocciata, meglio e quindi più pericolosamente. Ha senso solo se
    **dichiara quando non è sicuro**.
  * \[ ]  implementazione di traduzione con sostituzione grafica
  * \[x]  installare qwen tts e Chatterbox, provare sul banco e stimare l'hardware
    → **fatti tutti e due**, erano già installati nei venv delle cartelle sorelle.
    **Chatterbox**: 3394 ms a battuta su CUDA — fuori portata dal vivo, ma dà emozione
    continua e clonazione zero-shot. **Qwen3-TTS ONNX**: backend scritto
    (`speak/backends/qwen.py`), voci come **descrizioni**, italiano nativo.
  * \[x]  streaming di Qwen3-TTS
    → **fatto e verificato**: primo campione a **257 ms** invece di 4820, e i blocchi
    concatenati sono la battuta intera (`bench_qwen --pezzi`: stessi campioni di
    `synthesize`, giunture a 0,89× dell'errore di fondo). Regge il tempo reale (0,83×,
    zero `mix.underrun` su 25 battute). Si vocoda il **prefisso** e si consegna la coda:
    misurato, `vocoder(codici[:k])` è trasparente (corr 1,0000) mentre il blocco interno
    no (corr 0,95).
    → **Ma il motore resta inutilizzabile dal vivo, per un'altra ragione.** Sulla stessa
    scena da 49 s e sulle stesse 25 battute, Qwen produce **77 s di parlato contro i 35
    di Piper** — 8,4 car/s contro 18,3. Non ci sta nemmeno comprimendo al tetto (WSOLA
    inchiodato a 1,250, latenza p50 3,6-6,7 s contro 533 ms). Lo streaming ha risolto la
    latenza al primo campione; **non può risolvere una voce che parla la metà**.
    Qwen non ha controllo di velocità (`rate` gli arriva e lo ignora).
    → **Le due leve provate tutte e due.** La fretta chiesta *a parole* nella descrizione
    della voce funziona ma poco (8,4 → 9,6 car/s nella catena vera; «parla svelto» non fa
    niente, serve una descrizione concreta — sillabe fitte, nessuna pausa). Alzando anche
    `timing.rate_max` a 1,45 la scena rientra: **86% invece del 125%, latenza p50 2,2 s
    invece di 6,7**. Ma il criterio dichiarato prima della prova era «sopra 13-14 car/s
    torna in gioco» e il motore sta a 10,8, e ci arriva solo con WSOLA ben oltre l'1,3
    dove le consonanti spariscono. **Il numero dice no; decide l'ascolto.**
    → **Le descrizioni vanno scritte in inglese** (il testo da dire resta italiano):
    misurato contando il sesso che esce, italiano 4-5/8 voci giuste, inglese **7/8**. In
    italiano le voci femminili uscivano a 159-164 Hz, cioè maschili.
    → **L'hardware che serve, misurato**: il costo è **banda di memoria** (6,12 GB riletti
    per ogni 80 ms di audio; il tempo segue i byte, 33/67 contro 23/77). Sulla 4060 sono
    0,75× tempo reale, cioè il 25% di margine — e **a GPU occupata va a 9,6×**. Serve
    ~670 GB/s e 16 GB: **4070 Ti SUPER / 4080 / 3090 e oltre** (la 3090 usata è la via
    economica). Il motore resta **integrato ma spento di default**: chi ha la scheda lo
    accende con `--set tts.backend=qwen`.
  * \[ ]  adattamento speaker per tutti i giochi (nome del parlante scritto a schermo)
    → vale la latenza: toglierebbe i 500 ms di `decide_after_ms`, che oggi costano **il
    doppio della sintesi**. Non misurabile su questa registrazione: GTA V i nomi non li scrive.
  * \[x]  adattamento per gtaV se il sottotitolo contiene una parola colorata
    → **fatto e acceso** (`vision.min_color_word_frac = 0.15`). Il difetto vero non era la
    frase saltata, era **la frase sporcata**: frammenti di HUD colorata incollati dentro il
    sottotitolo e pronunciati (`'Rec.Lavoriamo insieme...'`, `"Sì, era lui.Adam'a App"`).
    Dal vivo: **69 battute contro 66, neutre 14 contro 18**, e l'OCR legge meglio anche il
    resto (`': olta'` → `'svolta'`).
* **Step finali**

  * \[ ]  UI interfaccia chiara e funzionale
  * \[ ]  possibilità di modificare i sottotitoli tradotti colore dimensione
  * \[ ]  scegliere lingua input lingua output
  * \[ ]  selettore delle tecnologie da usare
  * \[ ]  impostazioni avanzate con regolazione di tutti i parametri con vicino un icona a ogni settings che spiega bene cosa fa e cosa succede se viene cambiato rischi ecc
  * \[ ] cambiamento live dei settings e applicazione live
  * PRIMA DI INIZIARE LA FASE SEGUENTE FAMMI FARE UNA PROVA e ti faccio un report dettagliato di cosa va e cosa no
  * \[ ]  rendere il tutto facilmente installabile plug and play
  * \[ ]  fare exe
  * \[ ]  scegliere la licenza copyright da usare in base alle librerie e la mia scelta
  * \[ ]  repo github senza collaboratore claude

    * \[ ]  repo professionale dove spiega tutte le feature e lingue supportate
    * \[ ]  spiegazione con un diagramma di flusso di cosa avviene nel programma
    * \[ ]  valorizzazione dell'uso completamente locale ed estrema privacy
    * \[ ]  scrivere requisiti minimi richiesti, e quelli per la migliore esperienza in assoluto
    * \[ ]  fare anche un link paypal o qualcosa del genere per prendere delle donazioni
    * \[ ]  fare sito github dove c'è spiegato tutto
    * \[ ]  fruttare hype di gtavi per dire che è compatibile anche con quello
