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

1. **Uno che scarica il repo e fa doppio clic, cosa vede?** ❌ Niente: serve la
   riga di comando. Un `livedub.bat` che chiama il venv è mezz'ora. **[fatto]**
2. **Se manca Python 3.11 lo dice o esplode?** ✅ `installa.ps1` lo controlla per
   primo e si ferma con il link.
3. **Se manca la GPU?** ✅ `-SenzaGpu`, e senza il flag lo dichiara verificando
   il provider CUDA vero.
4. **Se manca OneOCR?** ✅ Lo dice e spiega che si userà `ppocr`, che legge peggio.
5. **I modelli si scaricano al primo avvio: l'utente lo sa prima o dopo?** ❌ Lo
   scopre quando la finestra sembra bloccata. Serve una barra di avanzamento.
6. **Quanto pesa un'installazione completa?** ❓ Mai misurato. `du -sh` dopo un
   giro pulito.
7. **Funziona su un utente Windows senza diritti di amministratore?** ❓ Probabile
   (nessun servizio, nessun driver), mai provato.
8. **Funziona con Python installato dal Microsoft Store?** ❓ Quel Python ha una
   `sys.prefix` virtualizzata: è il caso che rompe i venv più spesso.
9. **Se la cartella ha uno spazio o un accento nel percorso?** ❓ Qui il percorso
   di sviluppo ha già un `!` e regge, ma non è una prova.
10. **Disinstallare cosa lascia in giro?** ❌ `models/` (fino a 2 GB) e `runs/`.
    Nessuno lo dice. Una riga nel README.

## B. La finestra (11–25)

11. **Se Windows è in tema chiaro?** ✅ **[fatto]** La finestra lo segue e cambia
    in diretta, con sei colori dei personaggi rifatti per il bianco.
12. **Se lo schermo è a 125% o 150%?** ❓ Qt gestisce lo scaling da solo, ma
    nessuno ha guardato la finestra a 150%.
13. **Su uno schermo 1366×768 ci sta?** ❌ La finestra parte a 1240×800. Serve un
    minimo sensato e un `resize` che rispetti lo schermo. **[fatto]**
14. **La finestra si ricorda dov'era e quanto era grande?** ❌ Riparte sempre al
    centro. **[fatto]**
15. **Le impostazioni cambiate si perdono chiudendo?** ❌ **Sì, tutte.** È il
    difetto più grave di questa lista: un'ora di regolazioni buttata. **[fatto]**
16. **Si può salvare una configurazione con un nome?** ❌ Solo scrivendo un JSON a
    mano in `profiles/`. **[fatto]**
17. **C'è un modo di sapere che versione si sta usando?** ❌ No, e senza non si
    può leggere un rapporto di errore di nessuno. **[fatto]**
18. **Scorciatoie da tastiera?** ❌ Nessuna. Almeno Ctrl+S, Ctrl+F, F5. **[fatto]**
19. **Si può usare senza mouse?** ❓ Qt dà il Tab di serie; mai provato in ordine.
20. **Un cieco con uno screen reader?** ❌ Nessuna etichetta accessibile dichiarata.
21. **Chiudendo mentre gira, la sessione si chiude bene?** ❓ Nella Tk sì (c'è
    `chiudi`); nella Qt il caso non esiste ancora.
22. **Se si preme Avvia due volte?** ✅ Nella Tk `if self.threads: return`.
23. **Il log cresce all'infinito?** ❌ Sì, `QPlainTextEdit` senza tetto: una
    sessione lunga se lo mangia tutto. **[fatto]**
24. **Si può copiare una riga del log?** ✅ È un widget di testo selezionabile.
25. **Si può cercare dentro il log?** ❌ No.

## C. Configurazione (26–38)

26. **166 parametri sono troppi per chiunque?** ❌ Sì: manca una vista "le dieci
    che contano". La ricerca aiuta ma presume che tu sappia il nome.
27. **Un valore fuori scala può rompere la catena?** ❌ `Config.set` controlla il
    **tipo**, non l'intervallo: `capture.fps = -5` passa.
28. **Un valore assurdo ma valido?** ❌ `decide_after_ms = 99999` è accettato e
    rende il programma muto senza dire perché.
29. **Le spiegazioni ci sono per tutti i campi?** ❌ 50 su 166 non ce l'hanno, e
    c'è un cricchetto che impedisce che aumentino.
30. **Un profilo di gioco scritto male cosa fa?** ✅ Una chiave sconosciuta è un
    errore all'avvio, non un refuso silenzioso.
31. **Si può tornare indietro da una modifica?** ❌ Solo "Riporta ai default", che
    è tutto o niente. Manca un annulla.
32. **Due finestre aperte insieme si pestano i piedi?** ❓ Scriverebbero nello
    stesso `runs/` e nello stesso `cast.json`.
33. **Cambiare motore TTS a caldo?** ✅ La striscia "Applica ora" rifà la catena.
34. **Un parametro cambiato è davvero quello in uso?** ✅ Ogni manopola rilegge da
    config dopo aver scritto.
35. **Si può esportare la configurazione per un rapporto di errore?** ❌ Esiste
    `--dump-config` ma non un bottone. **[fatto]**
36. **La ROI disegnata a mano è sensata?** ✅ Sopra 0,12 di altezza la finestra
    avvisa, con la misura del perché.
37. **Le aree multiple si possono disegnare col mouse nella Qt?** ❌ Partono dalla
    ROI: manca il selettore.
38. **Il profilo caricato si vede da qualche parte?** ✅ `profile` in cima alle
    impostazioni.

## D. Audio (39–50)

39. **Se il device audio sparisce a metà (cuffie staccate)?** ❓ Mai provato. È il
    guasto più probabile in assoluto durante una partita.
40. **Se cattura e uscita sono lo stesso device?** ✅ Si rifiuta di partire e lo
    spiega: rientrerebbe.
41. **Se non c'è nessun loopback?** ❓ `find_loopback` cosa fa a mani vuote.
42. **Voicemeeter non installato?** ✅ Il loopback WASAPI di serie basta.
43. **Il doppiaggio rientra nella cattura?** ✅ Il controllo sui device lo impedisce.
44. **`mix.underrun` viene mostrato all'utente?** ❌ Sta nel rapporto di fine
    sessione: durante, non lo vede nessuno.
45. **Il volume del gioco torna su se il programma muore?** ❌ No: il ducking è
    nel nostro mixer, quindi muore con lui — ma allora esce l'audio originale
    intero, che è il comportamento giusto.
46. **Cosa succede a 44,1 kHz invece di 48?** ❓ `audio.samplerate` è dichiarato
    ma la catena è misurata a 48000.
47. **Con l'audio a 5.1 o 7.1?** ❓ Mai provato; `center_enabled` presuppone stereo.
48. **La latenza audio è stabile per ore?** ❓ Le sessioni misurate sono da minuti.
49. **Se il gioco è muto, il riconoscimento impazzisce?** ✅ Sotto soglia diventa
    voce neutra invece di inventare un personaggio.
50. **Il file WAV della sessione quanto pesa?** ❓ ~10 MB/minuto a 48 kHz stereo
    float, mai dichiarato all'utente.

## E. Video e cattura (51–62)

51. **Se il gioco è a schermo intero esclusivo?** ✅ Documentato: serve finestra o
    borderless. ❌ Ma il programma non lo **rileva**, lo si scopre da un video nero.
52. **Se il gioco cambia risoluzione durante la partita?** ❓ La ROI è normalizzata,
    quindi in teoria regge; mai provato.
53. **Se si sposta la finestra del gioco?** ✅ La ROI è relativa alla finestra.
54. **Se si minimizza il gioco?** ❓ WGC su una finestra minimizzata dà fotogrammi
    vuoti: l'OCR gira a vuoto e consuma.
55. **Due monitor con scaling diverso?** ❓ Classico caso che rompe le coordinate.
56. **Il programma legge se stesso?** ✅ Risolto alla radice catturando la sola
    finestra del gioco; verificato a 0,000.
57. **L'OCR gira anche quando non c'è nulla da leggere?** ✅ `max_ocr_hz` e il diff.
58. **Su un gioco che scrive scuro su chiaro?** ❌ Legge ma sporca (misurato su
    fotogrammi costruiti). Mai su un gioco vero.
59. **Sottotitoli non in una striscia (fumetti)?** ❌ Non previsto.
60. **Lingue non latine?** ❓ OneOCR le legge, ma la catena a valle no.
61. **Se la ROI include un orologio o un contatore?** ❌ Verrebbe letto e detto.
62. **Il costo dell'OCR su un PC lento?** ✅ Misurato per numero di core.

## F. Voce e tempi (63–72)

63. **Se il modello di voce non si scarica?** ❌ `make_tts` solleva: la finestra
    mostrerebbe un errore grezzo.
64. **Se due battute si accavallano?** ✅ Una voce alla volta, con la fretta in volo.
65. **Se il testo è lunghissimo?** ✅ Il tetto sulla compressione, e il taglio.
66. **Se il testo è una sola parola?** ✅ Sotto `min_ocr_chars` non si dice.
67. **Il pool finisce le voci?** ✅ Si spostano i semitoni; `max_speakers = 16`.
68. **Un personaggio cambia voce a metà partita?** ✅ Le identità si fondono, e
    vince chi ha più battute.
69. **Le voci si ricordano fra sessioni?** ✅ `runs/cast.json`, con il nome.
70. **Il doppiaggio arriva sempre in ritardo di 1,2 s: si può dire all'utente?**
    ❌ Non c'è nessun indicatore di latenza in finestra.
71. **Se WSOLA schiaccia troppo, si sente?** ✅ Sì, ed è il motivo del tetto.
72. **Si può ascoltare una voce prima di scegliere?** ❌ Manca un "prova la voce".

## G. Traduzione (73–80)

73. **Se la rete cade con `google`?** ✅ Si tiene l'originale invece di restare muti.
74. **L'utente sa che con `google` il testo esce dal PC?** ✅ Dichiarato su stderr
    e nel README. ❌ Ma non nella finestra, dove si sceglie.
75. **I modelli locali ammorbidiscono le parolacce?** ✅ Misurato: 0/6 col template
    puro. Dichiarato.
76. **La traduzione rallenta la catena?** ✅ Misurato: la parte fissa passa da 670
    a 1690 ms.
77. **Se la lingua di partenza è sbagliata?** ❓ Nessun controllo.
78. **Il sottotitolo tradotto copre quello originale?** ✅ Verificato a schermo.
79. **Su fondo chiaro il riquadro sbaglia colore?** ✅ Misurato (fino a 86 livelli),
    ed è per questo che si usa il blur.
80. **La traduzione si può disattivare al volo?** ✅ È un campo caldo.

## H. Errori, guasti, diagnosi (81–90)

81. **Se qualcosa esplode, l'utente cosa vede?** ❌ Nella Qt un traceback in
    console che con l'exe non esiste. Serve un gestore globale. **[fatto]**
82. **C'è un file di log su disco?** ❌ Solo il rapporto di fine sessione. **[fatto]**
83. **Un rapporto di errore contiene versione, config e sistema?** ❌ **[fatto]**
84. **Se il disco è pieno?** ❓ `Session` scrive senza controllare.
85. **Se `runs/` diventa enorme?** ❌ Nessuna pulizia, nessun avviso.
86. **Il programma si accorge di essere in ritardo cronico?** ✅ I contatori ci
    sono. ❌ Ma non arrivano in faccia a nessuno.
87. **Un thread che muore ferma tutto o resta a metà?** ❓ Il video ha `on_error="bypass"`;
    l'audio no.
88. **Si può riprodurre una sessione andata male?** ✅ `tools/reopen`, ed è il
    pezzo forte del progetto.
89. **Le metriche di finestra finiscono nel rapporto?** ✅ Corretto: prima morivano.
90. **Un crash lascia il file audio rotto?** ❓ Mai provato a uccidere il processo.

## I. Prestazioni e risorse (91–96)

91. **Quanta RAM usa una sessione lunga?** ❓ Mai misurato.
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
93. **Quanto ruba al gioco in fps?** ❓ Mai misurato con un frame counter.
94. **La VRAM di Kokoro (1128 MB) su una scheda da 6 GB con GTA V acceso?** ❓
95. **Il programma scalda la CPU al punto di far throttlare il gioco?** ❓
96. **Chiudendo, tutti i processi figli muoiono?** ❓ Il worker OneOCR è un figlio.

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
| ✅ a posto, verificato | 40 |
| ❌ difetti veri | 32 |
| ❓ mai provato | 28 |

**I ❓ sono la parte interessante.** Ventinove domande a cui nessuno ha risposto,
e quasi tutte si chiudono in mezz'ora ciascuna con una misura. Le tre che
chiuderei per prime, perché riguardano una sessione di gioco vera e non un caso
di bordo:

1. ~~la memoria cresce in tre ore?~~ **fatta**: +10,4 MB, e il tetto messo.
2. **le cuffie staccate a metà partita** (39) — è il guasto più probabile di tutti;
3. **quanto ruba al gioco in fps** (93) — è la domanda che decide se uno lo tiene
   acceso o no.
