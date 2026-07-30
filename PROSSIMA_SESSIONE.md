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

**Attenzione**: `graphify.exe` è bloccato da un criterio di controllo
applicazioni su questa macchina. Se serve, si legge `graph.json` direttamente con
tre righe di Python. Il grafo è fermo al 28 luglio: le tre sessioni successive
non ci sono dentro.

## Il banco di chi parla, che adesso c'è

È lo strumento con cui è stato fatto tutto il lavoro sulle voci, e va usato
**prima** di cambiare qualunque soglia del riconoscimento.

```powershell
# una volta per registrazione: costa una passata di OCR (~3 minuti)
.\.venv\Scripts\python.exe -m tools.dub testGameplayFattoDaMe.mp4 --profile gtav `
    --start 1240 --end 1340 --set vision.ocr_backend=oneocr `
    --dump-speaker runs\banco\speaker.jsonl

# tutte le altre: 50 millisecondi l'una
.\.venv\Scripts\python.exe -m tools.recluster runs\banco\speaker.jsonl --profile gtav
.\.venv\Scripts\python.exe -m tools.recluster runs\banco\speaker.jsonl --profile gtav `
    --sweep speaker.merge_similarity 0.50:0.95:0.025
.\.venv\Scripts\python.exe -m tools.recluster runs\banco\speaker.jsonl --profile gtav --shuffle
.\.venv\Scripts\python.exe -m tools.recluster runs\banco\speaker.jsonl --profile gtav `
    --wav testGameplayFattoDaMe.mp4 --offset 1240     # un WAV per identità, da ascoltare
```

`--shuffle` è **il numero che decide**: le stesse impronte permutate fra le
battute, dove nessuna identità esiste più. Se una soglia fonde là quanto qui, non
sta fondendo identità.

`voce_per` in `speak/pool.py` contiene la politica di assegnazione, e sta lì e
non nella pipeline proprio perché il banco deve rigiocare **quella vera**. Se la
sposti, il banco comincia a misurare un doppiaggio che non esiste.

## Stato: cosa funziona

Scena del concessionario, 44 battute in 100 s, tre personaggi reali (confermati
all'ascolto: S9 e S11 sono la stessa persona, e sono tutti e tre uomini).

| | prima | adesso |
|---|---|---|
| identità con una voce | 4 | **3**, quanti sono |
| uomini con voce femminile | 1 (quello con più battute) | **0** |
| battute che cambiano voce | — | **0** |
| battute dette in attesa di sapere | — | 4 |
| latenza sottotitolo→voce (Piper) | ~570 ms | invariata |

Tre cose nuove, tutte misurate sul banco:

1. **le identità si fondono** (`speaker.merge_similarity = 0.70`). La soglia
   viene dalla colonna del permutato: sotto 0,625 il rumore fonde quanto
   l'identità — sedici identità diventano dieci, e sono dieci gruppi a caso —
   sopra 0,775 non fonde più niente. Dentro la finestra c'è **una** fusione,
   sempre la stessa. Vince chi ha più battute, non chi è comparso prima;
2. **il genere si decide quando si sa**: servono quattro misure, la mediana ha
   sostituito la media mobile, e finché non si sa si parla con una voce **fuori
   dal pool** che nessuno terrà;
3. **SuperTonic non si interrompe più**: la velocità che gli arrivava era 2,08 e
   lui accetta 2,0 — sollevando `ValueError`, cioè uccidendo la sessione alla
   battuta 10 di 44.

## Le due cose che il banco ha scoperto e che cambiano il piano

**L'intonazione presa sui ritagli del gioco non misura la voce.** Sui quindici
ritagli di Lamar ci sono 64 finestre sonore fra 90 e 130 Hz — lui — e 673 sopra i
190, che sono la scena. E non sono finestre incerte: tenendo solo quelle con
autocorrelazione sopra 0,6 la stima **peggiora**, da 221 a 230 Hz. Nessuna media
di quel numero può tornare giusta. Il rimedio sfrutta la forma della
contaminazione — il fondo aggiunge periodicità alte, non ne aggiunge di basse —
quindi `stima_f0` prende il quindicesimo percentile delle finestre invece della
mediana. **Il prezzo è dichiarato: questa taratura sa dire "uomo" molto meglio di
"donna", e su una registrazione con voci femminili va rifatta** (soglie in
`listen/speaker.py`, ripiego in `speaker.gender_fallback`).

**Le undici identità con una battuta sola non sono il difetto che sembravano.**
Non ricevono mai una voce — non sono confermate, quindi `scegli` non le propone
mai — quindi non si sentono: sporcano il report e basta. E la fusione dei
centroidi non può recuperarle: la loro somiglianza con le identità grandi sta fra
0,17 e 0,58, dove il permutato fonde quanto il vero, e il secondo candidato è
spesso a un centesimo dal primo (S13: 0,516 contro 0,507). Nascono quasi tutte
nei primi trenta secondi, quando la banca è povera. Se un giorno danno fastidio,
la domanda da farsi è **cosa contiene quel ritaglio**, non quale soglia usare.

## Cosa resta aperto, in ordine

1. **SuperTonic è tagliuzzato, e la colpa non è sua.** Misurato in isolamento,
   senza gioco e senza scheduler: al suo passo naturale fa 16,0 caratteri al
   secondo, come Piper. La catena lo guida a **26,4** — 1,36 chiesti al modello
   più 1,25 di WSOLA — e a quel ritmo nessuna voce articola. La prova sta in
   `dub.rate_x1000`, che con SuperTonic vale **1250 a ogni percentile**: tutte e
   quarantaquattro le battute compresse al tetto, mentre con Piper la mediana è
   1023. Togliere i 500 ms di attesa non lo cura (provato: la latenza peggiora,
   p50 789 ms e p95 3025, perché la coda si accumula — `dub.overflow` 30). Il
   lavoro sta nello **scheduler e nel modello di durata**, non nel TTS: perché la
   finestra di ogni battuta risulti sempre troppo stretta di un fattore 1,25.
   Finché non è sciolto il default resta `piper`.
2. **La partenza lenta.** Le prime 13 battute su 44 vanno tutte a `S0` perché
   finché nessuno ha parlato due volte non esiste un confermato. Trenta secondi
   di scena con una voce sola. Il rimedio ovvio — abbassare la conferma a una
   battuta — è precisamente il difetto che la conferma è stata scritta per
   impedire, e costava tredici voci in cento secondi. Da provare invece: la voce
   neutra anche qui, così i primi trenta secondi dichiarano "non lo so ancora"
   invece di mentire.
3. Le voci femminili: la taratura del genere non è calibrata su una donna,
   perché in questa registrazione non ce n'è. Serve una scena che ne contenga.

## Comandi

```powershell
.\.venv\Scripts\python.exe -m tools.selftest                 # 796 verifiche
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

Non toccare i 500 ms di attesa senza rimisurare: c'è una tabella in
`SpeakerConfig.decide_after_ms` che dice cosa si perde a ogni valore. È già stato
provato a toglierli per curare SuperTonic, e non è quella la cura.

## Le lezioni di metodo, che valgono più del codice

**Il caso nullo migliore condivide tutto tranne la risposta.** Le impronte
permutate fra le battute lasciano identiche la scena, i tempi e l'alternanza, e
tolgono solo *chi è chi*. Sono loro che hanno fissato la soglia della fusione: a
0,50 il conteggio delle identità scendeva da sedici a undici e sembrava un
trionfo, ma il permutato scendeva a undici anche lui.

**Una misura può essere incapace di esprimere la risposta giusta.** L'intonazione
sul mix del gioco è il caso più netto: le finestre *più sicure* sono quelle
sbagliate, quindi filtrare per confidenza peggiora la risposta. Quando succede,
la via d'uscita non è una statistica più robusta ma la **forma** dell'errore —
qui il fatto che contamini in una direzione sola.

**Guardare ogni lettura, non solo quelle che arrivano in fondo.** «Lamar prende
paola» non si spiegava dal report finale, dove la sua f0 è 166 Hz, maschile. Si
spiegava stampando la storia della decisione: alla seconda misura era 218 e il
sesso era già dichiarato, con la voce data e non più toccabile.

**Verificare in isolamento prima di accusare il modello.** SuperTonic sembrava
inservibile. Sintetizzate le stesse battute senza gioco e senza scheduler, il suo
passo naturale è quello giusto: a tagliuzzare è la catena che gli chiede 26
caratteri al secondo.

**E la più importante: l'orecchio dell'utente trova ciò che la suite non può.**
Anche in questa sessione: la suite era verde su 796 verifiche e SuperTonic era
inascoltabile. Quando l'utente dice "non funziona" e i numeri dicono di sì,
**sono i numeri a essere sotto esame**.

---

Fine del prompt.
