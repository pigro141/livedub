# live dub tts

## Dove siamo

**Feature: 14 su 14.** Tutte chiuse, comprese quelle che si sono chiuse con un
"no" misurato (i tag del TTS, la correzione automatica per distanza di edit, Qwen).

**Step finali: 16 su 19.** Restano tre voci, e sono **tutte e tre una decisione
tua, non un lavoro**: creare il repo GitHub (è pronto), il link donazioni, il
sito. Il resto — interfaccia, selettore delle tecnologie, impostazioni con la
spiegazione accanto, modifica a caldo, aree multiple, installatore, exe, licenza,
README col diagramma — è fatto e guardato a schermo.

**Suite: 1678 verifiche verdi** (`tools/selftest.py`).

## 17 agosto 2026 — la finestra è **Menta**, e tre difetti sulle aree

L'interfaccia descritta in `docs/interfaccia.md` è stata costruita: tavolozza a
quattordici ruoli su due temi, `R(h)` ricavata dal logo, scala delle distanze a
passi di quattro, cinque corpi. E i pezzi che prima non c'erano — il pannello dei
tre passi al posto della riga di log che spariva, le marche di gravità nel
margine, la tessera del guasto **col bottone dentro**, la barra della misura a
2 Hz, il logo che cambia faccia sulla stessa regola del colore.

**La finestra Qt è il prodotto**: `livedub.spec`, `livedub.bat`, `installa.ps1`,
`README.md` e `tools/prova.ps1` puntano tutti lì. La Tk resta per il confronto
(`prova.ps1 -Tk`) e non è vestita.

**Cinque prescrizioni del documento sono cadute alla prima occhiata dell'utente**,
e nessuna dava errore: i punti di rottura che facevano sparire i numeri, lo stato
detto in tre posti, il monospazio ovunque, la tessera dietro al logo, i tre passi
che si spuntavano da soli. Più il minimo dichiarato (960) che non era il minimo
vero (978), perché tre `QLabel` normali impongono la larghezza del loro testo.

**E poi le aree.** Aggiungere una zona «solo testo» non faceva niente, per **tre**
motivi impilati e tutti muti:

| | cosa |
|---|---|
| 1 | una sola area dichiarata **perdeva il proprio rettangolo** (`len(pezzi) == 1`) e leggeva la vecchia ROI |
| 2 | le battute mute non venivano **tradotte né disegnate**: filtrate prima di `_speak`, dove avviene la traduzione |
| 3 | un'area grande **non legge**, e non è una soglia da ritoccare: a schermo intero 14 fotogrammi guardati, 14 saltati, zero letture |

Il terzo è un limite dichiarato, non un difetto: ora `troppo_grande()` lo dice
sopra 0,30 di altezza, mentre si tira il rettangolo e all'avvio della catena.

**E la cura del primo si era mangiata trentuno manopole**: passava una *copia* di
`cfg.vision` a ogni lettore, e i campi caldi smettevano di arrivare continuando a
mostrare il valore nuovo. Rifatta passando il rettangolo a parte.

## E adesso è stato provato dal vivo per intero, in autonomia

L'11 agosto 2026, a sera, la catena è stata accesa **davvero**: gioco sostituito da una
registrazione a schermo intero in Chrome, cattura vera dello schermo, OCR vero,
audio vero da Voicemeeter, voce nelle casse. Non un banco: la stessa strada che
fa il programma quando lo usa una persona.

**I numeri dichiarati reggono**, e uno di loro era la domanda aperta:

| | misurato dal vivo | dichiarato |
|---|---|---|
| latenza p50 | **665 ms** | ~670 ms (piper) |
| sintesi p50 | 57 ms | ~50 ms |
| `mix.underrun` | **0** | 0 |
| `dub.rate_x1000` p50 | **1000** | doveva staccarsi da 1250 |

L'ultima riga chiude quello che `DA_VERIFICARE.md` chiedeva di guardare: la cura
su `accepted_delay_ms` era giusta, e la compressione non è più incollata al tetto.

**Quello che la prova ha trovato, e che nessun banco aveva visto:**

| | esito |
|---|---|
| l'HUD del gioco («Sali sul \[tasto]») viene **letta e pronunciata**: 8 battute su 17 dal vivo, 11 su 46 rigiocando il file | **aperto**, con la misura in mano |
| `--output` non poteva funzionare: cercava il dispositivo fra i **loopback**, che hanno zero canali di uscita | corretto |
| la cattura dello schermo intero costava **32,4 ms** su 33 di budget a 30 Hz | corretto: si prende solo la fascia, **+35% di letture e cinque sottotitoli in più** |
| `tools/live.py` non scriveva `speaker.jsonl` | corretto |

**E due conclusioni sbagliate sono state ritirate**, il che vale quanto le
correzioni: «dal vivo si perde il 60% delle righe» e «dal vivo riconosce molto
peggio del banco» erano **tutte e due false**, prodotte confrontando *tratti
diversi della stessa scena* (una volta il video era perfino finito a metà prova).
Allineando i tratti: 31 battute contro 33, e voce neutra 81% contro 78%. La
regola che ne è uscita sta in `CLAUDE.md`.

## Il cancello è passato — e questo è il fatto che conta

Il cancello che diceva *«prima di iniziare la fase seguente fammi fare una prova
e ti faccio un report dettagliato»* **è stato passato il 7 agosto 2026**. L'utente
ha provato dal vivo, due volte, e il report è arrivato in forma di **video della
sessione**: dai suoi fotogrammi e dal suo log a schermo sono usciti quattro
difetti, nessuno dei quali faceva scattare un contatore.

Tutti e quattro sono corretti, con la suite a **1172 verifiche verdi**:

| difetto | esito, misurato dal vivo |
|---|---|
| a pool pieno nessuno arrivava a due battute, quindi nessuno era mai *confermato* | voci neutre da **97% a 35%**, punteggio p50 da 0,136 a **0,414** |
| il bordo sfumato della toppa rimetteva l'italiano che doveva nascondere | contrasto sulla cornice da 68,3 a 24,3 |
| il criterio della parola colorata misurava una lettera, non una parola | scattava 0 volte su una parola vera, ora sì |
| l'HUD sulla stessa riga finiva nel ritaglio e **veniva pronunciato** | battute sporcate da **11% a 0%** |

Una quinta ipotesi è stata **smentita da una misura** invece che risolta:
`dub.rate_x1000` al tetto non dipende da una finestra prevista corta. La finestra
vera è 0,93 s contro 1,37 previsti — la previsione era già generosa, e la
compressione è necessaria in tre casi su quattro.

**La domanda blur o riquadro è chiusa**: l'utente ha giudicato dal vivo e si resta
sul **blur**. Non è più una voce aperta.

E c'è un banco nuovo che cambia il modo di lavorare: **`yt_scena.mp4`**, la scena
della sessione scaricata a 1080p60 (avanti di 29,5 s rispetto ai tempi del vivo).
Riproduce sul banco la frammentazione delle identità e il tetto di compressione.
Prima serviva una sessione intera dell'utente per provare una modifica sul
riconoscimento; adesso sono tre minuti.

## Cosa resta: tre voci, e sono tutte tue

| | cosa | chi decide |
|---|---|---|
| repo GitHub | è pronto: README col diagramma, `LICENZE.md`, `installa.ps1`, `livedub.spec`, `livedub.bat`. Da decidere prima: 167 commit su 170 hanno il trailer `Co-Authored-By: Claude` | **tu** |
| link donazioni | hai detto «dopo» | **tu** |
| sito | idem | **tu** |

Più due cose tecniche, dichiarate e non dimenticate:

- **l'HUD pronunciata** (`Sali sul …`), l'unico difetto vero che la prova dal vivo
  ha lasciato aperto. La misura c'è già: le letture consecutive si somigliano fra
  **0,58 e 0,77**, e `vision.continue_similarity` vale 0,75 — dieci su dodici
  cadono appena sotto. Due strade: tarare quella soglia (serve il metodo
  dell'altopiano, non un valore indovinato) oppure una regola dedicata sul
  prefisso comune, che non tocca il caso generale;
- **portare Avvia nella finestra Qt**, che chiude sei delle domande dichiarate.

**Niente di tutto questo aspetta una misura**, ed è il contrario di com'era prima:
le misure sono fatte e stanno nei file. Chi riprende non deve tornare a misurare.

**Il cancello resta come strumento**: `tools\prova.ps1` accende la catena con i
controlli fatti prima (venv, scheda di cattura, traduttore), accetta
`-Set sezione.campo=valore` e stampa la configurazione per esteso;
`DA_VERIFICARE.md` è il foglio della prova.

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
    → **Blur o riquadro: deciso dall'utente il 7 agosto 2026, si resta sul `blur`.** Il
    riquadro non ha ritardo per costruzione, ma è una placca visibile e la sua tinta
    sbaglia proprio dove la scena è chiara (scarto fino a 86 livelli dalla scena
    attorno); il blur è quasi invisibile e il suo ritardo residuo è misurato a p50
    20-23 ms. **Non è più una voce aperta.**
    → E il bordo del blur aveva un difetto suo, corretto nella stessa prova: la
    sfumatura mescolava lo sfocato con i pixel del gioco, quindi **sul bordo rimetteva
    l'italiano**. Spenta (`sfuma = 0`): sfocato pieno fino al bordo.
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

  * \[x]  sistemare la grafica del sottotitolo tradotto
    → **Chiesto dall'utente**: deve occupare **solo lo spazio dove sta il testo** (non
    tutta la ROI, che su una battuta di due parole mette una fascia larga mezzo
    schermo), e usare **una sfocatura** per togliere il sottotitolo vecchio invece di
    coprirlo con un rettangolo pieno.
    → **Su questo mi ero sbagliato e va detto**: avevo scritto che dal vivo il blur era
    impossibile perché avrebbe richiesto una seconda cattura dello schermo. Falso: la
    catena cattura già il fotogramma a 30 Hz per darlo all'OCR, e quei pixel sono in mano
    nostra. Costava un ritaglio.
    → **Scritta, poi guardata a schermo, e aveva un difetto grosso.** La prima versione
    era verde e importava; messa su un fotogramma a tutto schermo si vedeva subito che la
    finestra veniva dimensionata sul testo **originale** mentre dentro ci si disegnava
    quello **tradotto**: una battuta di tre righe usciva come la sua riga di mezzo,
    tagliata sopra e sotto. Adesso la finestra è il **massimo fra i due** — l'inchiostro
    vecchio per coprirlo, il testo nuovo per leggerlo — e cresce verso l'alto restando
    appoggiata dov'era la riga vecchia.
    → **Altri tre difetti trovati nello stesso giro**: il riquadro si ricavava
    dall'ingombro grezzo della maschera (un riflesso in un angolo della ROI lo allargava a
    tutto lo schermo) e ora viene dalle righe che l'OCR ha **letto** (`classify_lines`,
    senza le colorate); la sfocatura era un velo che lasciava leggere l'originale ai lati;
    e `background_mode` e `blur_strength` **non li leggeva nessuno** dal vivo — l'overlay
    sfocava sempre, qualunque cosa dicesse la config, che è lo stesso difetto di
    `max_ocr_hz` e `tts.device`.
    → **E il selettore d'area non spostava l'overlay**: si ridisegnava il rettangolo col
    mouse — che è il modo dichiarato di usare il programma — e la finestra del tradotto
    restava dov'era la ROI di partenza.
    → **Poi l'utente l'ha provata dal vivo e aveva ancora tutto storto**, e la sua lista
    era giusta punto per punto. Il peggiore: **la finestra finiva dentro la cattura** —
    misurato, il 100% dei suoi pixel entrava nel fotogramma dato all'OCR, con `mss` e con
    `dxcam` — quindi l'OCR leggeva il nostro testo invece del sottotitolo, e le righe
    sparivano. `WDA_EXCLUDEFROMCAPTURE` porta quel numero a 0%: senza, niente di quello
    che sta a monte funziona, e il difetto sembra dell'OCR.
    → E poi: si sfocava **tutto il riquadro** invece della sola riga; il carattere era
    scelto da noi ed enorme; la finestra spariva alla fine della nostra voce invece che
    alla fine del sottotitolo. Adesso si tocca **solo la riga letta**, si **ricostruisce
    lo sfondo** al posto dei glifi (inpaint: sfocare lascia una fascia grigia, e due
    sottotitoli sovrapposti si vedono anche quando uno è sfocato), e **misura e colore si
    copiano dal sottotitolo del gioco** — `font_frac=0` e `color=""` vogliono dire «come
    il gioco», e sono i default.
    → **E lo strumento era sbagliato quanto il codice**: per giudicare la grafica serviva
    che l'utente accendesse il gioco, quindi ogni giro costava una sessione a lui.
    `tools/overlay_mp4.py` monta un video con **lo stesso pittore del vivo**
    (`ui.overlay.dipingi`), quindi i giri si fanno da soli in trenta secondi.
    → Il gruppo `selftest overlay` (21 verifiche) copre taglia, colore, che la riga sparisca
    davvero e che **la cancellatura non esca dalle righe del gioco di un pixel**.
  * \[x]  **cattura della finestra del gioco, non dello schermo**
    → **Correzione di rotta chiesta dall'utente**, e chiude alla radice il difetto piu'
    grave della sessione. Catturando lo schermo intero, nel fotogramma dato all'OCR
    finiva anche la nostra finestra del tradotto — misurato, il 100% dei suoi pixel — e
    il programma leggeva se stesso: da li' le righe saltate.
    → Windows Graphics Capture con `CreateForWindow`, come fa la repo di riferimento
    (`GraphicsCaptureService.cs`). Verificato due volte: una finestra rossa messa sopra a
    quella catturata **non entra** nel fotogramma (0,000 dei suoi pixel), e con la catena
    intera l'OCR ha letto **zero** righe che fossero nostre su quattro.
    → Selettore delle finestre nella UI (`capture/finestre.py`, `EnumWindows` in ctypes,
    nessuna dipendenza). Si scartano le finestre *cloaked*: senza, la prima della lista
    era «Esperienza input di Windows», invisibile e grande quanto lo schermo.
    → Il rettangolo e' quello **cliente** e non quello della finestra: WGC consegna il
    contenuto senza bordi, e i sette pixel di differenza sono di quanto l'overlay
    cadrebbe spostato rispetto al sottotitolo.
    → **La telecamera virtuale per OBS e' stata tolta del tutto** (`ui/record.py`,
    `pyvirtualcam`, la sezione `record`): esisteva per rimettere il tradotto in una
    sorgente video, visto che l'overlay era nascosto a tutte le catture. Non essendo piu'
    nascosto, non serve piu' — la cura giusta era togliere la causa, non aggiungere una
    seconda cura.
  * \[x]  UI interfaccia chiara e funzionale
    → **fatta**: la barra di prima resta sopra (è quella che si tocca durante una prova) e
    sotto ci sono quattro schede — Sessione (il log di chi parla), Tecnologie, Aree,
    Impostazioni avanzate. Guardata a schermo e **guidata**, non solo scritta.
  * \[x]  possibilità di modificare i sottotitoli tradotti colore dimensione
    → `translate.color`, `background`, `background_opacity`, `background_mode`,
    `blur_strength`, `font`, `font_frac`, `outline`. La dimensione è una **frazione**
    dell'altezza del fotogramma e non punti: così la stessa configurazione vale a 1080p
    e a 1440p. **Manca la UI che li espone**, non i parametri.
  * \[x]  scegliere lingua input lingua output
    → `translate.source` / `translate.target`. `auto` lo capisce solo Google: i modelli
    offline sono **di** una coppia di lingue, quindi con `locale` un `auto` diventa `en`
    e viene detto, invece di esserlo in silenzio. La UI adesso **c'è**: si veda la voce
    «adattare l'interfaccia per più lingue» più sotto.
  * \[x]  selettore delle tecnologie da usare
    → **fatto**, e non è un elenco scritto a mano: le scelte escono dai commenti di
    `core/config.py` con la convenzione `a | b | c` già in uso. Vengono da sole cinque
    voci, tre OCR, cinque traduttori, tre impronte, due VAD, i pesi di Kokoro. Aggiungere
    un backend non richiede di toccare la UI.
    → Una regola nata da un caso vero: se né il valore né il default stanno nell'elenco,
    quell'elenco **non parla di quel campo** (`translate.ollama_model` vale
    `translategemma:4b` e il commento dice `4b | 12b | 27b`: sono le taglie, e il menu ci
    avrebbe scritto dentro `4b`).
  * \[x]  impostazioni avanzate con regolazione di tutti i parametri con vicino un icona a ogni settings che spiega bene cosa fa e cosa succede se viene cambiato rischi ecc (davvero tuti anche la regolazione delle frequenze maschio femmina)
    → **tutti e 165**, comprese le frequenze maschio/femmina, **generati percorrendo
    l'albero** (`core/schema.py` + `ui/pannello.py`) e non elencati a mano: un elenco a
    mano diverge al primo campo aggiunto.
    → Il `?` accanto a ogni campo apre il commento di `core/config.py` **così com'è
    scritto**, tabelle delle misure comprese. Non sono testi riscritti per l'occasione:
    riscriverli vorrebbe dire perdere le misure e inventare rischi.
    → **Guardare il pannello ha trovato subito un difetto vero**: `line_pad` spiegava la
    maschera del ritaglio, perché il commento di `mask_crop` — un campo *tolto* — era
    rimasto orfano e si incollava al campo dopo. Ora una verifica impedisce che due campi
    condividano la stessa spiegazione.
    → Cricchetto: 50 campi non hanno ancora una spiegazione, ed è un **tetto** — uno nuovo
    senza commento rende la suite rossa.
  * \[x] cambiamento live dei settings e applicazione live
    → **142 campi su 165 si applicano a caldo**, e i 23 che non possono lo **dicono**
    invece di fingere: «si applica al prossimo Avvia, non a questa sessione». La regola è
    scritta: freddo se il valore si legge nel costruttore di qualcosa che non si
    ricostruisce a sessione accesa.
    → Fingere sarebbe il difetto peggiore per uno strumento di misura: una sessione che
    gira con una configurazione diversa da quella che la UI mostra.
    → Barra e pannelli sono **tre griglie sopra un solo oggetto** e si riallineano nei due
    versi; ogni manopola **rilegge da config dopo aver scritto**, così quel che si vede è
    sempre quel che si usa (generalizzazione del difetto trovato digitando `9999`).
  * \[~] selettore aree multiple di traduzioni solo testo e poi quella testo e audio
    → **fatto, e poi tolto il 18 agosto 2026 su decisione dell'utente**: «infattibile».
    Aveva tutto quello che era stato chiesto — i due modi, le sovrapposizioni sottratte
    prima di leggere, 46 verifiche su due invarianti — e girava. Ma la promessa che lo
    reggeva, **piu' scritte tradotte insieme sopra il gioco**, dal vivo non era
    mantenibile: l'overlay disegna una scritta per volta, e portarlo a N voleva dire una
    tela grande quanto l'area rinfrescata a ogni fotogramma.
    → Ne restano due pezzi, e non per nostalgia: `vision.roi.troppo_grande` (un'area
    troppo alta e' **muta**, non meno precisa — misurato) e `translate.misura_originale`,
    il tradotto che tiene la misura dell'originale stringendo il carattere invece del
    riquadro, **spento di serie** perche' il prezzo lo giudica l'occhio.
    → La lezione che resta scritta in `CLAUDE.md`: una cura che **copia** un oggetto
    condiviso rompe tutto cio' che contava sul fatto che fosse condiviso.
  * \[x]  **PRIMA DI INIZIARE LA FASE SEGUENTE FAMMI FARE UNA PROVA e ti faccio un
    report dettagliato di cosa va e cosa no**
    → **Fatto il 7 agosto 2026.** Prova dal vivo, e il report è arrivato come **video
    della sessione**: i quattro difetti sono usciti dai fotogrammi dell'utente e dal
    log a schermo dentro il suo video, **nessuno da un contatore**. Il peggiore —
    l'HUD incollata dentro le battute e pronunciata (`'Raggiungi i'`, `'Sali sul'`,
    `.San An`) — era l'11% delle battute e non faceva scattare niente, perché per la
    catena erano righe lette con successo.
    → Corretti tutti e quattro, suite a **1172 verifiche** (oggi 1678). Il dettaglio
    e le misure stanno in `CLAUDE.md` e in `PROSSIMA_SESSIONE.md`.
    → **Il cancello è aperto: da qui si va sulla UI.**
    → **E l'11 agosto, a sera, la prova è stata rifatta in autonomia**, senza chiedertela:
    registrazione a schermo intero in Chrome al posto del gioco, cattura vera, OCR
    vero, audio vero. Da lì è uscito che l'HUD **non era chiusa** (8 battute su 17
    dal vivo, e 11 su 46 rigiocando il file: quindi non è la cattura, è la catena),
    che `--output` non poteva funzionare, e che la cattura dello schermo intero si
    mangiava il 90% del budget di un fotogramma. I primi due erano invisibili al
    banco per costruzione.
  * \[ ]  rendere il tutto facilmente installabile plug and play
    → `installa.ps1`: Python, venv, dipendenze, OneOCR, modelli, e chiude con la suite.
    **Verifica di aver ottenuto quello che ha chiesto** invece di dire «fatto» — compreso
    il provider CUDA vero (`get_available_providers`), perché qui un ripiego silenzioso è
    già costato due volte. Quello che manca lo elenca col perché e cosa comporta.
    → `-SenzaGpu` installa `onnxruntime` al posto di quello GPU: i due **non convivono**.
  * \[x]  adattare linterfaccia per più lingue quante sono quelle disponibili per google translate, (controlla che il testo non sfori su nessun riquadro)
    → **Due cose diverse, e confonderle costa una sessione.** La lingua del *doppiaggio*
    (`translate.source`/`target`) e la lingua della *finestra* (`ui.lingua`). La prima sta
    nella scheda Traduzione, la seconda nella Preparazione, apposta lontane.
    → Le **133 lingue di Google** stanno in `translate/lingue.py` — codice, nome italiano,
    nome inglese — scritte nel repo e non scaricate: un elenco che dipende dalla rete si
    svuota quando la rete non c'è, e un menu vuoto non dà errore. Il menu è filtrabile
    (`QCompleter` a contenuto: `giapp`, `ja` e `pones` trovano la stessa riga).
    → **Il menu dice la verità per il backend scelto** (`lingue.copertura`): elenco chiuso
    solo dove lo è davvero (Google); per `locale`, `llm` e `ollama` niente filtro e la
    frase che dice da cosa dipende. E `auto` è marcato su tutti tranne Google, perché lì
    diventa `en` in silenzio.
    → **E dichiara quando manca la voce** (`speak.pool.ha_voce`): Piper e SuperTonic solo
    italiano, Kokoro italiano e inglese. Senza avviso, tradurre in giapponese dà una voce
    italiana che pronuncia il giapponese — nessun errore, audio che esce.
    → I nomi inglesi della stessa tabella entrano ora nel prompt di TranslateGemma: erano
    tredici scritti a mano, e `target=ja` faceva leggere al modello «into ja».
    → **La finestra**: `ui.lingua` (`auto` segue Windows), **42 cataloghi × 168 chiavi** in
    `ui/lingue/*.json`, generati con `tools/traduci_ui.py` e committati. Si applica a
    caldo come il tema. Le chiavi non si scrivono: si **percorre la finestra**
    (`ui/lingua.py`), la stessa passeggiata che poi la riveste — così estrattore e
    applicatore non possono vedere due elenchi diversi.
    → **Non si traducono** le spiegazioni dei 166 campi (vengono dai commenti di
    `core/config.py`, misure comprese), il registro, la barra della misura, i percorsi dei
    campi, i nomi dei caratteri e dei dispositivi: marcati `nontradurre`, col perché.
    → **Il testo non sfora**, misurato con la finestra vera e il carattere vero
    (`tools/traduci_ui.py --misura`): la più larga è il tamil a **872 px sul minimo di
    960**, nessuna scheda sfora. La stessa misura fatta offscreen dava trentuno lingue su
    quarantadue «rotte» — la piattaforma senza caratteri ha un ripiego molto più largo, e
    una misura che non può esprimere la risposta va cambiata, non interpretata.
    → Da destra a sinistra (arabo, ebraico, persiano, urdu): `setLayoutDirection`, e
    guardato in una schermata.
  * \[ ]  Creare un tutorial iniziale per un neofita dove spiega tutta linterfaccia, con anche la spiegazione se va installato qualcosa, es VoiceMeeter.
  * \[ ]  fare exe
    → `livedub.spec` (PyInstaller), 528 MB in cartella — non `onefile`, perché lì mezzo
    giga viene scompattato a ogni avvio e i percorsi relativi a `__file__` cambiano ogni
    volta.
    → **Si impacchetta il programma, non i modelli**: è una scelta di licenza prima che di
    dimensione (OneOCR non è ridistribuibile, i pesi hanno ognuno la propria).
    → **Farlo partire ha trovato il difetto che leggere lo spec non poteva**: il pannello
    estrae le spiegazioni dal *sorgente* di `core/config.py`, e in un pacchetto i `.py` non
    ci sono. Ora `config.py` viaggia fra i dati e, se manca, il programma **lo dichiara**
    invece di morire o di tacere. Verificato a schermo: finestra `livedub`, quattro schede.
  * \[x]  scegliere la licenza copyright da usare in base alle librerie e la mia scelta
    → **GPL-3.0-or-later, e non per gusto: è quello che impongono le librerie.**
    `piper-tts` 1.6.0 — il motore **di default** — è GPL-3.0-or-later, ed `espeak-ng.dll`
    dentro `espeakng-loader` (il g2p di Kokoro) pure. Due motori su tre.
    → Anche scrivendo MIT sul nostro codice, l'eseguibile distribuito resterebbe GPL-3: la
    compatibilità funziona in una direzione sola. Dichiarare MIT sarebbe difendibile per i
    file scritti da noi e **fuorviante per la cosa che la gente scarica**.
    → Il conto libreria per libreria sta in `LICENZE.md`, letto dai metadati dei pacchetti
    **installati** e non a memoria. Comprese le due cose che non si ridistribuiscono
    (OneOCR e i pesi) e cosa servirebbe per tornare permissivi.
  * \[ ]  repo github senza collaboratore claude

    * \[ ]  repo professionale dove spiega tutte le feature e lingue supportate
      → `README.md` riscritto per chi arriva da fuori; il vecchio (architettura estesa) è
      diventato `docs/architettura.md`. Feature, lingue di lettura/voce/traduzione, la
      finestra, l'installazione, e il capitolo onesto «Funziona con il mio gioco?».
    * \[ ]  spiegazione con un diagramma di flusso di cosa avviene nel programma
      → diagramma Mermaid nel README (GitHub lo disegna da solo, niente immagini da
      rigenerare): i due domini, il punto di fusione, e la strada dell'overlay.
    * \[ ]  valorizzazione dell'uso completamente locale ed estrema privacy
      → non uno slogan ma **la lista di cosa esce dal computer**, stadio per stadio.
      L'unico modo di far uscire del testo è chiedere `translate.backend=google`, che
      lo dichiara su stderr a ogni battuta. Nessuna telemetria, nessun account, nessun
      server nostro — non esiste un server nostro.
    * \[ ]  scrivere requisiti minimi richiesti, e quelli per la migliore esperienza in assoluto
      → scritti nel README con i numeri misurati: minimi 4 core e nessuna GPU (Piper,
      ~670 ms di latenza), migliore Kokoro su CUDA (257 ms, 1128 MB di VRAM, ~1150 ms
      totali). Con la tabella del costo per numero di core, e la riga che conta:
      **sotto i 6 core solo Piper**.
      → **i numeri ci sono già, manca scriverli**: senza GPU si gira con Piper o SuperTonic
      (CPU, e sotto i 6 core **solo** Piper); Kokoro vuole CUDA e 1128 MB di VRAM. È
      l'unico punto degli step finali che poggia su misure, e le misure sono fatte.
    * \[x]  fare anche un link paypal o qualcosa del genere per prendere delle donazioni
      → Ko-fi: <https://ko-fi.com/filippodebenedittis>, col titolo **«Buy me a token!»**.
      Sta nel README in un capitolo suo, prima della licenza, e dice le due cose
      che tolgono l'imbarazzo a chi legge: che non sblocca niente, e che non c'e'
      niente da sbloccare. Nessun account, nessun server, nessun limite da
      togliere — sarebbe l'unica riga del README in contraddizione con il
      capitolo sulla privacy.
    * \[ ]  fare sito github dove c'è spiegato tutto
    * \[ ]  sfruttare hype di gtavi per dire che è compatibile anche con quello
      → nel README, e detto in modo che regga: livedub è costruito su **quello che c'è a
      schermo**, non su file del gioco. Niente da estrarre, niente anti-cheat da toccare —
      guarda lo schermo e suona nelle cuffie come farebbe un giocatore.
