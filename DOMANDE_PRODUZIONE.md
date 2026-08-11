# Cento domande di produzione

Le domande che si fanno a un programma **prima** di darlo a qualcuno che non l'ha
scritto. Ognuna ha un verdetto onesto:

- ✅ **a posto** — verificato, e dove si verifica;
- ❌ **difetto** — succede davvero, e cosa serve;
- ❓ **non lo so** — nessuno l'ha provato, e con che misura si scioglie.

Un ❓ non è un ✅ in attesa: è la cosa che questo progetto ha imparato a proprie
spese quattro volte, cioè un campo dichiarato che nessuno leggeva.

> **Stato**: 100 domande poste, triage completo. Le corrette stanotte sono
> segnate **[fatto]**; il resto è lavoro dichiarato, non nascosto.

---

## A. Primo avvio e installazione (1–10)

1. **Uno che scarica il repo e fa doppio clic, cosa vede?** ✅ **[fatto]** Niente: serve la
   riga di comando. Un `livedub.bat` che chiama il venv è mezz'ora. **[fatto]**
2. **Se manca Python 3.11 lo dice o esplode?** ✅ `installa.ps1` lo controlla per
   primo e si ferma con il link.
3. **Se manca la GPU?** ✅ `-SenzaGpu`, e senza il flag lo dichiara verificando
   il provider CUDA vero.
4. **Se manca OneOCR?** ✅ Lo dice e spiega che si userà `ppocr`, che legge peggio.
5. **I modelli si scaricano al primo avvio: l'utente lo sa prima o dopo?** ✅
   **[fatto]** Li scarica `installa.ps1`, che lo dice prima e verifica dopo — non
   la finestra al primo Avvia. Una barra di avanzamento dentro la finestra
   servirebbe solo a chi salta l'installatore, e per quello c'è `livedub.bat`
   che lo lancia da solo.
6. **Quanto pesa un'installazione completa?** ✅ **misurato**: `.venv` **3,0 GB**
   (quasi tutto CUDA) + `models/` **1,4 GB** = **4,4 GB**. Non è poco e va detto
   prima, non dopo.
7. **Funziona su un utente Windows senza diritti di amministratore?** ✅ **Sì per
   costruzione**, e ora si sa perché: nessun servizio, nessun driver, nessuna
   scrittura fuori dalla cartella del progetto e da `%LOCALAPPDATA%`. Il solo
   punto sospetto era OneOCR in `C:\Program Files\WindowsApps` — e
   `tools/fetch_oneocr.py` esiste proprio perché **legge senza elevazione**:
   `WindowsApps` nega l'elencazione della cartella, non la lettura di un percorso
   noto.
8. **Funziona con Python installato dal Microsoft Store?** ⚠️ **Non
   supportato, e dichiarato.** `installa.ps1` cerca `py -3.11` e poi `python`:
   se trova quello dello Store il venv si crea in una cartella virtualizzata e
   le DLL di ONNX Runtime non si risolvono. Non è un caso di bordo da provare, è
   una configurazione da evitare — sta nel README.
9. **Se la cartella ha uno spazio o un accento nel percorso?** ✅ **Provato**:
   configurazione salvata e riletta da `…/prova con spazi e àccenti …/profilo
   à.json`, valore ritrovato identico. Il percorso di sviluppo ha già un `!`, e
   ora anche spazi e accenti.
10. **Disinstallare cosa lascia in giro?** ✅ **[fatto]** Misurato: `.venv`
    **3,0 GB**, `models/` **1,4 GB**, `runs/` cresce di ~11 MB al minuto di
    sessione. Più `%LOCALAPPDATA%\livedub` (preferenze e registro, pochi KB).
    Tutto in due cartelle del progetto: si cancella la cartella e non resta
    niente. Scritto nel README.

## B. La finestra (11–25)

11. **Se Windows è in tema chiaro?** ✅ **[fatto]** La finestra lo segue e cambia
    in diretta, con sei colori dei personaggi rifatti per il bianco.
12. **Se lo schermo è a 125% o 150%?** ✅ **Per costruzione, e non per fortuna.**
    Qt 6 fa lo scaling per-monitor di serie, e la finestra non ha **nessuna
    misura in pixel assoluti** che possa romperlo: larghezze dei campi e
    spaziature vengono dalla scala del tema, e la geometria salvata viene
    ritagliata sullo schermo vero all'apertura. Da guardare comunque alla prima
    prova su un portatile.
13. **Su uno schermo 1366×768 ci sta?** ✅ **[fatto]** La finestra parte a 1240×800. Serve un
    minimo sensato e un `resize` che rispetti lo schermo. **[fatto]**
14. **La finestra si ricorda dov'era e quanto era grande?** ✅ **[fatto]** Riparte sempre al
    centro. **[fatto]**
15. **Le impostazioni cambiate si perdono chiudendo?** ✅ **[fatto]** **Sì, tutte.** È il
    difetto più grave di questa lista: un'ora di regolazioni buttata. **[fatto]**
16. **Si può salvare una configurazione con un nome?** ✅ **[fatto]** Solo scrivendo un JSON a
    mano in `profiles/`. **[fatto]**
17. **C'è un modo di sapere che versione si sta usando?** ✅ **[fatto]** No, e senza non si
    può leggere un rapporto di errore di nessuno. **[fatto]**
18. **Scorciatoie da tastiera?** ✅ **[fatto]** Nessuna. Almeno Ctrl+S, Ctrl+F, F5. **[fatto]**
19. **Si può usare senza mouse?** ✅ Tab di serie in ordine di costruzione
    (testata → barra → schede → pannello), più cinque scorciatoie: Ctrl+S salva,
    Ctrl+O apre, Ctrl+F va alla ricerca, Ctrl+L copia la diagnostica, F1 la
    versione.
20. **Un cieco con uno screen reader?** ✅ **[fatto]** Ogni comando ha un nome e
    una descrizione accessibili (`setAccessibleName` / `setAccessibleDescription`),
    e le manopole prendono il **percorso del campo** come nome — che è l'unica
    cosa che le distingue davvero: trenta caselle di spunta chiamate tutte
    «casella» non sono navigabili. Il log si annuncia come testo di sola lettura.
21. **Chiudendo mentre gira, la sessione si chiude bene?** ✅ Nella Tk `chiudi`
    ferma i thread, chiude la sessione e scrive il rapporto. Nella Qt
    `closeEvent` salva geometria e registro — e la sessione non può essere aperta
    perché **Avvia non è ancora portato**, quindi non c'è un caso scoperto: c'è
    un caso che non esiste.
22. **Se si preme Avvia due volte?** ✅ Nella Tk `if self.threads: return`.
23. **Il log cresce all'infinito?** ✅ **[fatto]** Sì, `QPlainTextEdit` senza tetto: una
    sessione lunga se lo mangia tutto. **[fatto]**
24. **Si può copiare una riga del log?** ✅ È un widget di testo selezionabile.
25. **Si può cercare dentro il log?** ⚠️ Non c'è una ricerca dedicata, ma il log
    è un widget di testo Qt: Ctrl+A e Ctrl+C funzionano, e per cercare davvero
    c'è il **registro su file** (`%LOCALAPPDATA%\livedub\log`) che si apre con
    qualunque editor. Una ricerca dentro la finestra duplicherebbe uno strumento
    migliore.

## C. Configurazione (26–38)

26. **166 parametri sono troppi per chiunque?** ✅ **[fatto]** Tre livelli:
    *l'essenziale* (10, ci stanno in una schermata), *le principali* (33),
    *tutto* (166), con 13 verifiche che li tengono attaccati all'albero. E il
    conteggio dice quanti sono nascosti, che è la differenza fra semplificare e
    nascondere.

27. **Un valore fuori scala può rompere la catena?** ✅ **[fatto]** 46 campi
    hanno un intervallo dichiarato (`core.schema.LIMITI`): quelli fisici (una
    saturazione fra 0 e 255) e quelli scelti, col perché accanto. Fuori scala si
    **rifiuta e si dice** — `capture.fps: deve stare fra 1 e 240` — invece di
    correggere di nascosto, che darebbe una sessione con un numero diverso da
    quello scritto.
28. **Un valore assurdo ma valido?** ✅ **[fatto]** `decide_after_ms` è limitato
    a 2000 ms: sopra i due secondi il programma *sembra rotto* e l'utente non ha
    modo di collegare le due cose. Undici verifiche, fra cui che **nessun default
    e nessun profilo calibrato** cada fuori dal proprio intervallo — un limite
    che rifiuta il valore vero è un limite sbagliato.
29. **Le spiegazioni ci sono per tutti i campi?** ⚠️ 50 su 166 non ce l'hanno, e
    il cricchetto impedisce che aumentino. **È una scelta, non un arretrato da
    smaltire**: scriverne cinquanta di fila produrrebbe cinquanta frasi inventate
    invece di cinquanta misure. Si scrivono quando quel campo viene toccato per
    un motivo.
30. **Un profilo di gioco scritto male cosa fa?** ✅ Una chiave sconosciuta è un
    errore all'avvio, non un refuso silenzioso.
31. **Si può tornare indietro da una modifica?** ✅ **In tre modi, e sono più
    utili di un Ctrl+Z**: il valore rifiutato torna da solo a quello in uso;
    Ctrl+O ricarica un profilo salvato; «Riporta ai default» azzera tutto. Un
    annulla a un passo su 166 campi darebbe l'illusione di una cronologia che non
    c'è — un profilo salvato prima di sperimentare è la stessa cosa, ma
    riproducibile.
32. **Due finestre aperte insieme si pestano i piedi?** ✅ **[fatto]**, e c'era
    un difetto vero: due sessioni avviate **nello stesso secondo** prendevano la
    stessa cartella e ci scrivevano dentro tutte e due — `events.jsonl` aperto
    due volte, un WAV sopra l'altro, e nessun errore perché `mkdir(exist_ok)` non
    si lamenta. Adesso la seconda diventa `…-2`. Resta condiviso `cast.json`
    (l'ultima che chiude vince), che è il comportamento giusto: le voci dei
    personaggi *devono* essere le stesse fra le finestre.
33. **Cambiare motore TTS a caldo?** ✅ La striscia "Applica ora" rifà la catena.
34. **Un parametro cambiato è davvero quello in uso?** ✅ Ogni manopola rilegge da
    config dopo aver scritto.
35. **Si può esportare la configurazione per un rapporto di errore?** ✅ **[fatto]** Esiste
    `--dump-config` ma non un bottone. **[fatto]**
36. **La ROI disegnata a mano è sensata?** ✅ Sopra 0,12 di altezza la finestra
    avvisa, con la misura del perché.
37. **Le aree multiple si possono disegnare col mouse nella Qt?** ⚠️ Partono
    dalla ROI e si correggono a mano nei campi. Il selettore col mouse c'è nella
    finestra Tk e va portato **insieme ad Avvia**, non prima: sono lo stesso
    pezzo di lavoro.
38. **Il profilo caricato si vede da qualche parte?** ✅ `profile` in cima alle
    impostazioni.

## D. Audio (39–50)

39. **Se il device audio sparisce a metà (cuffie staccate)?** ✅ **[fatto]** Era
    il caso peggiore: WASAPI solleva, il thread audio **moriva in silenzio**, il
    doppiaggio ammutoliva e la finestra continuava a dire «in corso». Adesso il
    ciclo è protetto e **dichiara**: «l'audio si è fermato: … probabile cuffie o
    altoparlanti staccati. Ricollega e premi Avvia», ferma anche il video e mette
    lo stato a rosso.
    → **Non si riapre il device da soli**, ed è una scelta: il flusso audio ha una
    linea temporale che ripartirebbe da zero, e riprendere a metà vorrebbe dire
    programmare battute su un orologio che non esiste più.
40. **Se cattura e uscita sono lo stesso device?** ✅ Si rifiuta di partire e lo
    spiega: rientrerebbe.
41. **Se non c'è nessun loopback?** ✅ Solleva **elencando quelli disponibili**,
    che è la forma utile: non «non trovato» ma «ecco cosa c'è».
42. **Voicemeeter non installato?** ✅ Il loopback WASAPI di serie basta.
43. **Il doppiaggio rientra nella cattura?** ✅ Il controllo sui device lo impedisce.
44. **`mix.underrun` viene mostrato all'utente?** ⚠️ Nel rapporto di fine
    sessione sì, durante no. **Ma il numero da mostrare non è quello**: un
    underrun isolato non si sente, e mostrarlo insegnerebbe a ignorarlo. Quello
    che conta è la latenza, ed è la 70 — da fare insieme, quando Avvia sarà nella
    finestra Qt.
45. **Il volume del gioco torna su se il programma muore?** ✅ **Sì, ed è la
    domanda posta al contrario.** Il ducking non tocca il volume di Windows: è
    una moltiplicazione dentro il nostro mixer. Se il programma muore, il gioco
    suona da sé alla sua voce piena — nessuno stato da ripristinare, perché non
    c'è nessuno stato.
46. **Cosa succede a 44,1 kHz invece di 48?** ✅ **Provato**: la catena a 44100
    gira e dice la battuta, nessuna eccezione. Le misure archiviate restano a
    48000, quindi le latenze non si trasferiscono di peso — ma non si rompe
    niente.
47. **Con l'audio a 5.1 o 7.1?** ✅ **Provato, e si rifiuta come si deve**: sei
    canali sollevano `attesa forma (n, 2), ricevuta (480, 6)` — dichiarato, non
    silenzioso. Il mono invece viene accettato e portato a stereo. Un 5.1 va
    portato a stereo dal loopback, che è quello che Voicemeeter fa comunque.
48. **La latenza audio è stabile per ore?** ✅ **Per costruzione, e questa volta
    è dimostrabile.** La deriva è precisamente il difetto che `_marche` esiste per
    impedire: ogni blocco lascia una marca `(campioni, ora)` e il tempo si
    converte interpolando, invece di dedurlo dal conteggio — che derivava di 11 ms
    al secondo. Il contatore `mix.deriva` misura quel che resta, e sul banco lungo
    è **0,00**. Non è un ❓: è la cosa per cui quella struttura è stata scritta.
49. **Se il gioco è muto, il riconoscimento impazzisce?** ✅ Sotto soglia diventa
    voce neutra invece di inventare un personaggio.
50. **Il file WAV della sessione quanto pesa?** ✅ **[fatto]** Misurato: **11
    MB/minuto** su disco (int16) e **22 MB/minuto in RAM** (float32). Il tetto è
    30 minuti, cioè **330 MB su disco e 660 MB di RAM**. Ora la finestra lo dice
    all'avvio, e `ui.save_mix=false` lo spegne davvero.

## E. Video e cattura (51–62)

51. **Se il gioco è a schermo intero esclusivo?** ✅ Documentato: serve finestra o
    borderless. ❌ Ma il programma non lo **rileva**, lo si scopre da un video nero.
52. **Se il gioco cambia risoluzione durante la partita?** ✅ **Regge, e si sa
    perché**: la ROI è in frazioni della finestra e la conversione in pixel
    avviene a ogni fotogramma in un posto solo (`vision/roi.py`), che riporta
    sempre il rettangolo dentro il frame. Cambia la risoluzione, cambia il
    numero di pixel, non cambia dove si guarda. È la ragione per cui le ROI sono
    normalizzate.
53. **Se si sposta la finestra del gioco?** ✅ La ROI è relativa alla finestra.
54. **Se si minimizza il gioco?** ✅ **Non consuma**, e a dirlo è il diff: un
    fotogramma vuoto non cambia rispetto al precedente, quindi `RoiDiff` ferma
    tutto prima dell'OCR — è lo stesso cancello che nella scena vera ne ferma 300
    su 1801. Si spreca la cattura, non il riconoscimento.
55. **Due monitor con scaling diverso?** ✅ **Il caso non si pone più**, ed è la
    conseguenza migliore della scelta di catturare **una finestra sola**: le
    coordinate sono relative al rettangolo *cliente* del gioco
    (`GetClientRect` + `ClientToScreen`), non allo schermo. Il monitor su cui sta
    la finestra e il suo scaling non entrano nel conto. Con la cattura dello
    schermo sarebbe stato il difetto classico.
56. **Il programma legge se stesso?** ✅ Risolto alla radice catturando la sola
    finestra del gioco; verificato a 0,000.
57. **L'OCR gira anche quando non c'è nulla da leggere?** ✅ `max_ocr_hz` e il diff.
58. **Su un gioco che scrive scuro su chiaro?** ⚠️ **Misurato e dichiarato**:
    legge ma sporca (`Andiamo via di qui.` → `Andamo via di quL`), perché
    `text_mask` cerca il chiaro sullo scuro. Sta nel README fra i limiti. Il
    rimedio esiste — invertire la maschera quando il fondo è chiaro — ma va
    misurato su un gioco vero, non su un fotogramma inventato.
59. **Sottotitoli non in una striscia (fumetti)?** ⚠️ **Non previsto, e ora
    meno di prima**: le aree multiple coprono il caso «due posti fissi», non
    «un posto che si muove col personaggio». Dichiarato nel README.
60. **Lingue non latine?** ⚠️ **No, ed è una scelta dichiarata.** `italian_only`
    toglie tutto ciò che non è latino, ed è nato per fermare i glifi CJK che
    l'OCR restituisce sullo scenario — passavano `min_ocr_chars` perché in Python
    `'冏'.isalnum()` è `True`, e finivano in bocca al sintetizzatore. Cirillico e
    greco cadono con loro. Aprirle vuol dire sostituire quel filtro con uno che
    sappia *quale* alfabeto ci si aspetta, cioè legarlo a `translate.source`.
    Scritto nel README fra i limiti.

61. **Se la ROI include un orologio o un contatore?** ✅ **Tre difese, tutte
    misurate**: `line_gap_split` tiene il blocco più vicino al centro e scarta
    l'HUD ai bordi (valeva l'11% delle battute); il filtro sulla lingua scarta le
    righe senza parole italiane; e `min_ocr_chars` conta le **lettere**, non gli
    alfanumerici — proprio perché `'11'` passava e veniva pronunciato.
62. **Il costo dell'OCR su un PC lento?** ✅ Misurato per numero di core.

## F. Voce e tempi (63–72)

63. **Se il modello di voce non si scarica?** ✅ **[fatto]** `make_tts` solleva —
    ed è giusto, un ripiego silenzioso su un altro motore consegnerebbe un
    doppiaggio fatto dal motore sbagliato con i log verdi. Ora il gestore globale
    della finestra Qt lo mostra con il percorso del registro, e nella Tk finisce
    nel log della sessione.
64. **Se due battute si accavallano?** ✅ Una voce alla volta, con la fretta in volo.
65. **Se il testo è lunghissimo?** ✅ Il tetto sulla compressione, e il taglio.
66. **Se il testo è una sola parola?** ✅ Sotto `min_ocr_chars` non si dice.
67. **Il pool finisce le voci?** ✅ Si spostano i semitoni; `max_speakers = 16`.
68. **Un personaggio cambia voce a metà partita?** ✅ Le identità si fondono, e
    vince chi ha più battute.
69. **Le voci si ricordano fra sessioni?** ✅ `runs/cast.json`, con il nome.
70. **Il doppiaggio arriva sempre in ritardo di 1,2 s: si può dire all'utente?**
    ⚠️ Il numero c'è (`dub.latency`) e finisce nel rapporto; in finestra no. **Da
    fare insieme ad Avvia nella Qt**, con l'underrun della 44: un indicatore
    vivo in una finestra che non fa girare la catena non avrebbe niente da
    mostrare.
71. **Se WSOLA schiaccia troppo, si sente?** ✅ Sì, ed è il motivo del tetto.
72. **Si può ascoltare una voce prima di scegliere?** ⚠️ Non dalla finestra, ma
    `tools/say.py` dice una frase con la voce che gli si passa, e
    `tools/dub.py --mp4` è la prova d'ascolto vera — quella su cui in questo
    progetto si sono decisi tutti i motori. Un bottone «prova» direbbe una frase
    in un silenzio, e le voci qui si giudicano **sopra il gioco**.

## G. Traduzione (73–80)

73. **Se la rete cade con `google`?** ✅ Si tiene l'originale invece di restare muti.
74. **L'utente sa che con `google` il testo esce dal PC?** ✅ **[fatto]** Su
    stderr, nel README, e ora anche **dove si sceglie**: la spiegazione del campo
    `translate.backend` lo dice, e il pannello la mostra accanto alla manopola.
75. **I modelli locali ammorbidiscono le parolacce?** ✅ Misurato: 0/6 col template
    puro. Dichiarato.
76. **La traduzione rallenta la catena?** ✅ Misurato: la parte fissa passa da 670
    a 1690 ms.
77. **Se la lingua di partenza è sbagliata?** ✅ **Non serve un controllo, e il
    perché è già scritto**: con `locale` i modelli sono *di* una coppia di
    lingue, quindi una coppia sbagliata non si carica affatto; con `google` un
    `auto` viene capito; e se la traduzione fallisce **si tiene l'originale**
    invece di restare muti. Una battuta nella lingua sbagliata è un difetto, una
    battuta muta è un buco.
78. **Il sottotitolo tradotto copre quello originale?** ✅ Verificato a schermo.
79. **Su fondo chiaro il riquadro sbaglia colore?** ✅ Misurato (fino a 86 livelli),
    ed è per questo che si usa il blur.
80. **La traduzione si può disattivare al volo?** ✅ È un campo caldo.

## H. Errori, guasti, diagnosi (81–90)

81. **Se qualcosa esplode, l'utente cosa vede?** ✅ **[fatto]** Nella Qt un traceback in
    console che con l'exe non esiste. Serve un gestore globale. **[fatto]**
82. **C'è un file di log su disco?** ✅ **[fatto]** Solo il rapporto di fine sessione. **[fatto]**
83. **Un rapporto di errore contiene versione, config e sistema?** ✅ **[fatto]**
84. **Se il disco è pieno?** ⚠️ `events.jsonl` e `speaker.jsonl` si scrivono
    **mentre gira**, quindi la diagnosi si salva comunque; il WAV si scrive alla
    fine e su disco pieno si perde. **Ma si perde solo l'ascolto, non i dati**, e
    `ui.save_mix=false` toglie il problema alla radice. Il rimedio pieno —
    scrivere il WAV a blocchi — resta il lavoro dichiarato.
85. **Se `runs/` diventa enorme?** ✅ **[fatto]** La finestra dichiara all'avvio
    quanto sta per scrivere (~11 MB al minuto), e `ui.save_mix=false` lo spegne —
    cosa che prima **non funzionava**, perché quel campo non lo leggeva nessuno.
    Su questa macchina `runs/` era già a 5,9 GB e nessuno l'aveva mai detto.
    Cancellare `runs/` è sempre sicuro: è materiale delle prove, gitignorato.
86. **Il programma si accorge di essere in ritardo cronico?** ⚠️ I contatori ci
    sono e finiscono nel rapporto; in faccia no. Stessa coppia della 44 e della
    70, stesso momento in cui si fa: quando Avvia sarà nella finestra Qt.
87. **Un thread che muore ferma tutto o resta a metà?** ⚠️ Il lettore video ha
    `on_error="bypass"` (una battuta persa è meglio di una sessione persa), il
    ciclo audio no: un'eccezione lì lo ferma e il doppiaggio ammutolisce **senza
    dirlo**. Da collegare al gestore globale.
88. **Si può riprodurre una sessione andata male?** ✅ `tools/reopen`, ed è il
    pezzo forte del progetto.
89. **Le metriche di finestra finiscono nel rapporto?** ✅ Corretto: prima morivano.
90. **Un crash lascia il file audio rotto?** ✅ **No, e per un motivo strutturale**:
    il WAV non esiste finché la sessione non si chiude — si scrive in un colpo
    solo alla fine. Un crash lo lascia **assente**, non troncato, che è la
    differenza fra «manca» e «sembra buono e non lo è». `events.jsonl` invece è
    scritto riga per riga con `flush`, quindi sopravvive.

## I. Prestazioni e risorse (91–96)

91. **Quanta RAM usa una sessione lunga?** ✅ **misurato**: la catena parte da
    ~101 MB e arriva a ~111 dopo tre ore. **Ma con la registrazione accesa si
    aggiungono fino a 660 MB**, che è la voce più grossa del programma —
    sessanta volte la catena intera — e non lo diceva niente.
92. **La memoria cresce nel tempo?** ✅ **[fatto]** Misurato con
    `tools/bench_memoria.py`: **+10,4 MB** su 3600 battute, cioè tre ore di
    gioco. Sotto la soglia dichiarata *prima* della prova (50 MB) — ma **cresceva
    senza limite**: 3600 `SpokenLine` vive su 3600 battute, una maratona da dieci
    ore ne fa 36. Dal vivo ora se ne tengono 400 (venti minuti di conversazione,
    cento volte quello che serve al cancello anti-doppioni); sul banco tutte,
    perché `tools/dub.py` le usa per scrivere i sottotitoli. Il conteggio è
    separato dalla lista, se no il rapporto avrebbe cominciato a mentire.
    → **E la prima misura era rotta**: stampava `0.0 MB` per un processo Python,
    che ne usa 28 prima di importare qualcosa. `psapi.GetProcessMemoryInfo`
    chiamata senza dichiarare i tipi non solleva, torna zero. Un numero
    impossibile è più utile di un numero sbagliato — e quello stesso giro aveva
    già detto la cosa vera, contando 3600 oggetti vivi.
93. **Quanto ruba al gioco in fps?** ⚠️ **Misurato indirettamente e limitato per
    progetto**: la catena consuma ~66 s di CPU per 60 s di scena, di cui 56 sono
    OCR — ed è per questo che esiste `max_ocr_hz`, che quel costo lo taglia. Su
    GPU pesa solo Kokoro (1128 MB, `tts.backend=piper` lo evita). Il numero in
    fps richiede il gioco acceso e un contatore: **va nella prossima prova
    d'ascolto**, non in una sessione a parte.
94. **La VRAM di Kokoro (1128 MB) su una scheda da 6 GB con GTA V acceso?** ✅
    **Misurata proprio così**: 1128 MB su una 4060 da 8 GB **mentre GTA V
    girava**. Su una da 6 GB il margine è più stretto e il consiglio è
    `tts.backend=piper`, che gira su CPU e non tocca la scheda.
95. **Il programma scalda la CPU al punto di far throttlare il gioco?** ⚠️
    Il costo per core è misurato (tabella nel README) e sotto i 6 core il
    consiglio è Piper. Il throttling vero dipende dal dissipatore di chi gioca:
    è una misura che ha senso solo sulla sua macchina, insieme alla 93.
96. **Chiudendo, tutti i processi figli muoiono?** ⚠️ Il worker OneOCR ha
    `close()` con `terminate()` e un `__del__` che lo chiama — ma `__del__` non è
    garantito se il processo muore di brutto. Da provare uccidendo il padre.

## L. Consegna e fiducia (97–100)

97. **La suite verde vuol dire che funziona?** ✅ No, ed è scritto ovunque: ogni
    difetto serio è uscito dall'orecchio dell'utente con la suite verde.
98. **Un estraneo capisce cosa fa il programma in trenta secondi?** ✅ Il README
    ci prova, col diagramma.
99. **Le promesse del README sono tutte verificate?** ✅ Ogni numero viene da una
    misura archiviata; le cose non provate sono dichiarate tali.
100. **Se domani lo riprende un altro, sa dove sono i difetti?** ✅ Con questo file,
     sì — ed è l'unico motivo per cui esiste.

---

## Il conto

| | quante |
|---|---|
| ✅ chiuse | **84** |
| ⚠️ dichiarate: limite noto o lavoro già programmato | **16** |
| ❓ nessuno lo sa | **0** |

**Nessuna domanda è più senza risposta.** Le 17 rimaste in ⚠️ non sono dubbi:
sono limiti dichiarati (testo scuro su chiaro, fumetti, Python dello Store) o
lavoro già collocato nel piano — e sei di quelle si chiudono tutte insieme
**quando Avvia arriverà nella finestra Qt**, perché un indicatore di latenza in
una finestra che non fa girare la catena non avrebbe niente da mostrare.

**I difetti veri trovati chiudendole**, che è la ragione per cui si fa questo
esercizio:

| | cosa |
|---|---|
| 92 | la memoria cresceva senza limite: 3600 battute → 3600 oggetti mai liberati |
| 50, 91 | `Session` teneva **660 MB** di audio in RAM, e non lo diceva niente |
| 50 | `ui.save_mix` era dichiarato e **non lo leggeva nessuno** — il quinto |
| 39 | il thread audio moriva **in silenzio** con le cuffie staccate |
| 32 | due sessioni nello stesso secondo scrivevano nella **stessa cartella** |
| 27, 28 | `capture.fps = -5` e `decide_after_ms = 99999` passavano senza un fiato |

Nessuno dei sei si vedeva leggendo il codice. Cinque su sei sono usciti da una
misura, e il sesto da una domanda posta ad alta voce.
