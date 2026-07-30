# Prompt per la prossima sessione

Copia da qui in giù.

---

Lavoro su **livedub** (`C:\Users\filde\Documents\!code\CLAUDE\livedub`), doppiaggio
italiano live dei sottotitoli di GTA V. Leggi `CLAUDE.md` e basta: **non leggere
il README per intero**, costa e non serve.

## Usa il grafo come memoria, non grep

`graphify-out/graph.json` contiene le misure e i difetti, non solo il codice. Per
qualunque domanda su architettura, dipendenze, "dove sta X", "cosa rompo se tocco
Y", o su un difetto già trovato, interroga il grafo invece di partire a grep.

Nodi utili da cui partire: `sparizione-su-un-frame`, `cancello-anti-ripetizione`,
`due-porte-del-tracker`, `attesa-500ms`, `genere-deciso-troppo-presto`,
`identita-frammentate`, `oneocr-processo-separato`, `anti-alias-identita`,
`domanda-sbagliata-embedding`.

**Attenzione**: `graphify.exe` è bloccato da un criterio di controllo
applicazioni su questa macchina (`ApplicationFailedException` da PowerShell,
`Permission denied` da bash). Se serve, o lo sblocchi tu, o si legge
`graph.json` direttamente con tre righe di Python.

## Stato: cosa funziona

La catena gira dal vivo, si ascolta, e i due difetti che rovinavano le prove sono
chiusi. Ultima prova dal vivo, 78 battute in 164 s di dialogo:

| | |
|---|---|
| OCR | **OneOCR**, testo italiano leggibile per intero |
| doppioni | **spariti** (uno solo residuo, sotto la soglia di somiglianza) |
| latenza sottotitolo→voce | p50 ~650 ms (500 sono attesa voluta, vedi sotto) |
| sfori | rari; a volte l'italiano finisce **prima** dell'inglese |

Due garanzie indipendenti contro i doppioni, entrambe misurate:

1. `vision.vanish_frames` — il diff non può più dichiarare sparito un
   sottotitolo su un frame solo. Causa vera: l'inchiostro si misura col
   contrasto locale dei glifi, e una scena chiara dietro il testo lo fa crollare
   per un frame; il tracker chiudeva d'autorità e la lettura dopo riapriva lo
   **stesso identico testo**;
2. `cfg.repeat` — cancello finale: normalizza a sole lettere, confronta con le
   battute dette negli ultimi 6 s, sopra 0,90 non pronuncia. Forma presa da
   RSTGameTranslation (`C:\Users\filde\Documents\!code\RSTGameTranslation`, open
   source, gira su questa macchina con lo stesso OneOCR e non ha doppioni).

**I 500 ms di attesa servono solo a riconoscere chi parla.** Alla comparsa del
sottotitolo quel personaggio non ha ancora emesso un suono. Misurato: senza
attesa un personaggio su tre riceve la voce giusta **zero volte**; con 500 ms
l'accordo col giudizio dell'orecchio passa da 65,9% a 91,5%. Togliendo il
riconoscimento si torna a 263 ms.

## Il lavoro di questa sessione: separare le voci come attori

Il riconoscimento **funziona in laboratorio e si sfalda dal vivo**. Sulla
registrazione, raggruppando le battute di una scena, i gruppi risultano
all'ascolto una persona ciascuno e si ritrovano identici a sei minuti di
distanza — confermato dall'utente. Dal vivo, sulla **stessa scena**, il report
finale dice:

    16 identità per 3 personaggi reali (Franklin, Lamar, Simeon)
    Simeon sparso fra S3, S6, S8   Franklin fra S0 e S4
    11 identità con una battuta sola
    5 voci assegnate

Tre difetti distinti, in ordine di quanto si sentono:

**1. Le identità non si fondono mai.** Se il tracker spezza un personaggio in
due, restano due per sempre. I centroidi però si arricchiscono battuta dopo
battuta, e due frammenti della stessa persona diventano sempre più simili: a quel
punto si possono unire, **tenendo la voce del più anziano** (una voce che cambia
a metà scena è il difetto peggiore di tutti). È il lavoro con più margine.

**2. Il genere è deciso prima di conoscerlo.** `Personaggio.gender` viene
dall'intonazione, ma la voce si assegna alla **prima apparizione**, quando l'f0 è
stimata su uno o due ritagli rumorosi. Prova: nel report finale S3 ha
`f0 155 Hz -> m` e ha ricevuto `paola+2`, femminile. L'f0 si stabilizza dopo, ma
la voce è già data e non si tocca più. Da fare: mediana su N misure invece della
media mobile, e **rinviare l'assegnazione** finché il genere non è confidente,
usando intanto una voce neutra. Occhio: in scena rumorosa (spari, sirene) l'f0
aggancia il rumore e dichiara "femminile" per uomini — misurato, 187-273 Hz su
personaggi maschili.

**3. Le voci si somigliano.** Le tre maschili sono `riccardo` a 0 e ±2,5
semitoni: anche assegnate bene, l'orecchio fatica. **SuperTonic ha cinque voci
maschili native** (`speak/backends/supertonic.py`), i modelli (~398 MB) non sono
ancora scaricati. È il rimedio più diretto alla percezione di "voci a caso".

E la partenza lenta: finché nessuno ha parlato due volte non c'è nessun
confermato, quindi le prime battute vanno tutte sulla prima voce. Nella prova
sono i primi ~30 s.

## Comandi

```powershell
.\.venv\Scripts\python.exe -m tools.selftest                 # 742 verifiche
.\.venv\Scripts\python.exe -m tools.ui --profile live --loopback voicemeeter --set vision.ocr_backend=oneocr
.\.venv\Scripts\python.exe -m tools.dub testGameplayFattoDaMe.mp4 --profile gtav --start 1240 --end 1340 --mp4 --set vision.ocr_backend=oneocr
.\.venv\Scripts\python.exe -m tools.bench_speaker --clean
.\.venv\Scripts\python.exe -m tools.reopen runs\<data> [secondo]
```

`tools/ui.py` è la finestra: selettore d'area col mouse, avvia/ferma, log
colorato per personaggio. **Il rettangolo disegnato a mano è il percorso di
produzione** — l'utente finale farà così — quindi non si torna ai profili
calibrati per far tornare i conti.

`tools/dub.py` doppia una registrazione su file senza gioco, e con `--mp4`
produce il video con la traccia doppiata: è il modo di giudicare il sincro a
freddo. Verifica che l'uscita **differisca** dall'audio di ingresso, perché una
volta produceva un file identico all'originale mentre i log dicevano 46 battute
doppiate.

Le prove dal vivo si fanno sul **video di GTA V in Chrome a schermo intero**,
audio su VoiceMeeter, uscita sulle cuffie. Chiedi all'utente di far ripartire il
video prima di lanciare.

## Cosa fare, in ordine

1. **Fondere le identità.** Punto 1 qui sopra. È il margine grosso.
2. **Genere robusto e assegnazione rinviata.** Punto 2.
3. **SuperTonic**, cinque voci maschili native invece di tre pitch-shift.
4. La partenza lenta, se dopo 1–3 si sente ancora.

Non toccare i 500 ms di attesa senza rimisurare: c'è una tabella in
`SpeakerConfig.decide_after_ms` che dice cosa si perde a ogni valore.

## Le lezioni di metodo, che valgono più del codice

**Il caso nullo migliore condivide tutto tranne la risposta.** Un embedding sul
gioco dava EER 27% e sembrava un riconoscitore debole; lo stesso protocollo sui
**lati** del segnale stereo — dove il dialogo per costruzione non c'è — dava
25,0% dove il centro dava 25,0. Non era debole: non stava riconoscendo niente.

**Una misura può essere incapace di esprimere la risposta giusta, non solo
quella sbagliata.** La prima curva confrontava due ritagli *brevi* fra loro e
costruiva i negativi da due momenti qualunque: in un dialogo i personaggi si
alternano, quindi metà erano la stessa persona. Nessun riconoscitore poteva
prendere più di quel voto. Riformulata come la pone il tracker — ritaglio breve
contro **centroide** — la risposta è 100% a 0,75 s.

**Guardare l'ingresso prima di accusare il modello, sempre.** OneOCR sembrava
inservibile (7 battute contro 46): riceveva un ritaglio preparato per un
riconoscitore *senza* rilevatore. Col ritaglio intero torna a 45.

**Verificare in isolamento prima di installare.** `winocr` nel venv di
produzione ha rotto `onnxruntime` — niente ECAPA, niente Piper, niente
RapidOCR. Si guarda `pip install --dry-run --report` **prima**.

**E la più importante, dimostrata quattro volte oggi: l'orecchio dell'utente
trova ciò che la suite non può.** L'anti-alias che non filtrava, la misura che
confondeva "stessa voce" con "stesso momento", il doppiaggio programmato in un
futuro irraggiungibile, e i doppioni da sparizione — nessuno trovato dalle
verifiche. Quando l'utente dice "non funziona" e i numeri dicono di sì, **sono i
numeri a essere sotto esame**.

---

Fine del prompt.
