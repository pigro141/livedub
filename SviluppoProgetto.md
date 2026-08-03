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
    continua e clonazione zero-shot. **Qwen3-TTS ONNX**: gira a **0,66× tempo reale**,
    quindi in streaming la latenza sarebbe **320-430 ms** contro i 174 di Kokoro, cioè
    **è vivibile su GPU consumer**. Backend scritto (`speak/backends/qwen.py`), voci come
    **descrizioni**. **Manca lo streaming**: senza, costa 3,1 s a battuta.
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
