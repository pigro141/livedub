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

## La prova che non ha provato niente, e va rifatta meglio

Il soffitto del segnale: l'idea era separare il parlato dal fondo e vedere se il
riconoscimento migliora. Fatto con `HDEMUCS_HIGH_MUSDB_PLUS` dal venv `.venv-f5`
di `gta-redub-live` (`torchaudio.load` lì dentro non funziona — torchcodec non
carica la sua DLL — si legge il WAV col modulo standard e si aggira).

**Il separatore non ha separato niente**, e i numeri lo dicono senza appello:
correlazione 0,983 fra il centro originale e lo stem «vocals», rms al 96%, e
nelle pause del dialogo il «separato» è più **forte** dell'originale. L'istogramma
dell'intonazione è identico: mediana 191 contro 192 Hz, quota di finestre sopra
190 Hz 50% contro 51%.

Quindi il raggruppamento non migliora — 16 identità in entrambi i casi — ma
**questo non dice niente sull'ipotesi**: il trattamento non è stato applicato.
HDEMUCS è addestrato su musica (MUSDB), e su dialogo con effetti mette tutto
dentro «vocals». Serve un modello di *speech enhancement*, non un separatore
musicale: DTLN, RNNoise, o la variante `dns48` di Demucs. Sono anche i soli
candidati sensati per il vivo, perché girano in tempo reale.

Il controllo che rende leggibile questa prova è `runs/banco_orig.jsonl`: le
stesse impronte ricalcolate sull'audio **originale** con lo stesso script. Non
riproduce esattamente il dump della pipeline (16 identità invece di 15, perché il
ritaglio parte da `t_on` e non dall'onset del VAD), ed è proprio per questo che
serve: l'unica differenza attribuibile è quella fra `banco_orig` e `banco_voci`.

## Cosa resta aperto, in ordine

1. **L'ascolto.** Tutto quello che sta qui sopra è misurato ma non ascoltato.
   `runs\finale_piper\dub.wav` e `runs\finale_supertonic\dub.wav` sono la stessa
   scena con i due motori. Le domande da fare all'orecchio: SuperTonic articola
   le battute intere adesso? La voce neutra a metà scena dà fastidio? I 752 ms di
   SuperTonic si sentono contro i 589 di Piper?
2. **Una prova dal vivo**, che è un'altra cosa dal banco: `tools/ui.py`, video di
   GTA V in Chrome a schermo intero, VoiceMeeter, cuffie.
3. **La pulizia del segnale fatta con lo strumento giusto** (vedi sopra). È
   quello che alzerebbe insieme il riconoscimento, il genere e forse l'attesa di
   mezzo secondo.
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
