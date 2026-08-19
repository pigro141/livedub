Lavoro su **livedub** (`C:\Users\filde\Documents\!code\CLAUDE\livedub`),
doppiaggio italiano dal vivo dei sottotitoli dei videogiochi.

## La prima cosa: il grafo è la memoria

In `graphify-out/graph.json` c'è la mappa della codebase. Per **qualunque**
domanda architetturale — dove sta X, cosa rompo se tocco Y, chi chiama cosa — si
interroga quello **prima** di partire a grep:

```
graphify query "<domanda>"
```

Costruirlo è caro, interrogarlo no. **È stato ricostruito da zero il 18 agosto**,
dopo la rimozione delle aree: un `--update` si sarebbe rifiutato di rimpicciolire
il grafo, ed è il caso in cui il rebuild è la strada giusta. Conosce quindi la
finestra a cinque schede, `ui/tutorial.py`, `ui/lingua.py`, `translate/lingue.py`
e i 41 cataloghi.

Si riaggiorna con `/graphify . --update` **dopo** modifiche grosse, non prima di
ogni task.

## Dove siamo

Suite verde a **1889 verifiche**. `SviluppoProgetto.md`: **17 step su 19**.

### Il 19-20 agosto: il bug delle «battute in ritardo» erano **tre bug**

Chiuso, e **verificato dal vivo dall'utente** («torna tutto e va bene»), non sul
banco. Suite verde a **1889**.

Il sintomo era uno solo e durava da settimane: le battute escono sempre piu' in
ritardo, i sottotitoli smettono di essere letti finche' non si fa **alt-tab**, e
alla fine la finestra si pianta. Sotto c'erano tre cause indipendenti, e nessuna
delle tre era dove si era guardato prima.

**1. `b2a6557` + `4d0ce52` — ogni Avvia lasciava accesa la cattura di quello
prima.** I callback di WGC sono chiusure su se stessi e il ciclo video non
chiamava mai `close()`: la sorgente restava viva per tutto il processo e
continuava a copiare la finestra del gioco a ogni fotogramma. Cinque Avvia = **5
catture accese, 285 copie al secondo invece di 57**, e il costo si vedeva a
valle: sintesi da 162,9 a 180,4 ms, `classify_lines` da 30 a 47.

| | prima | dopo (dal vivo) |
|---|---|---|
| 1ª passata | 962 ms | 908 ms |
| 4ª-5ª passata | **8580 · 9453 ms** | **1984 · 1290 ms** |
| peggior caso | **46938 ms** | 5346 ms |
| `vision.classify` | 30 -> 47 ms | **33-37 ms, piatto** |

La quarta passata di controllo aveva **146 battute** — la piu' lunga della
giornata — e stava a 1290 ms. `mix.underrun` 0 in tutte.

**2. `a15ae1b` — `Motore.acceso` mentiva durante la partenza.** Valeva
`bool(self.threads)`, e i thread nascono in fondo a `_prepara`: per tutti i
secondi in cui si aprono i device e si carica il TTS il motore diceva «fermo»
mentre stava partendo. Un Ferma o un RIPROVA li' dentro faceva salire una
**seconda catena**, e i bottoni di una rimettevano quelli dell'altra — da cui lo
stato che l'utente ha visto: sessione «avviata», Ferma spento, Avvia acceso, e
Avvia che non fa niente. Ora `Motore.stato` (quattro stati) + `core.motore.bottoni()`
sono la fonte unica, **fuori da Qt**, e i bottoni la leggono invece di dedurla.

**3. Il cancello del diff normalizzava sull'area, e l'utente aveva ragione.**
Era stato scritto in questo file che un'area troppo alta e' «muta» come se fosse
un limite legittimo da aggirare tirando il rettangolo stretto. Non lo e': un
sottotitolo occupa **lo stesso numero di pixel** che l'area sia stretta o larga,
quindi dividere per l'area e' la **sesta** volta della forma «una soglia misurata
su una distribuzione e applicata a un'altra». Il cancello ora non normalizza piu':
con l'area a 0,95 le comparse viste passano da **33 a 42 su 44**, e a 0,06 e
0,187 non cambia niente (43 e 44 battute, identiche prima e dopo). Vale il
criterio dell'utente: **area piu' larga = meno precisione, ma legge sempre**.
Il consiglio «tirala stretta» resta, ma solo per la qualita' del blur.

Misurato che il cancello **non deriva nel tempo** (200 cicli identici danno lo
stesso risultato all'inizio e alla fine): erano davvero tre difetti distinti, e
non sono stati forzati in uno.

**E Argos era gia' il default**, non c'era niente da promuovere — ma il commento
di `translate.backend` adesso porta la misura che lo sceglie, che e' il **p95 e
non il p50**: la traduzione avviene dentro i 500 ms di attesa, quindi cio' che
sta sotto e' gratis e cio' che li supera si paga intero. Argos p95 **67 ms**,
google **1188**. Dal vivo: google 9 battute anticipate su 65 e 1828 ms di
latenza, Argos **65 su 65** e 962 ms.

### La notte del 18-19 agosto: tre commit, e il piu' importante non era in programma

**`5a569b8` — si traduce mentre si aspetta di sapere chi parla, non dopo.**
Nasce da una tua impressione («con Kokoro sembra in ritardo di una battuta»), che
era **giusta**: misurato sulle sessioni archiviate, l'audio della battuta N parte
col sottotitolo N+1 gia' a schermo nel **21% dei casi**. Ma la causa non era
Kokoro — la sintesi e' **245 ms su 1523** — ed era la **traduzione**, che stava
in fila *dopo* i 500 ms di `decide_after_ms` invece che *dentro*. Due attese
indipendenti messe in coda: una vuole il **testo** (c'e' subito), l'altra vuole
l'**audio**. Ora `core/anticipa.py` prepara il testo durante l'attesa.

E la sorpresa: **i 657 ms non erano google, erano ollama**. Google costa 98-498
ms ed e' **bimodale** (54 ms di p50 in una passata, 763 in un'altra a mezz'ora di
distanza) — verificato che non siamo noi: una apertura di connessione ogni dodici
chiamate, cache che funziona. E' la rete, ed e' il motivo per cui **coprirla**
dentro l'attesa e' la cura giusta invece di ottimizzare il client.

⚠️ **I numeri «dopo» sono una proiezione, non una misura.** Il banco non puo'
esprimere questo cambiamento (con l'orologio virtuale la traduzione non e' mai
stata addebitata, e `dub.latency` risulta identica al centesimo prima e dopo).
Vengono dal rigiocare la programmazione delle sessioni **dal vivo** archiviate:
p50 atteso **893-919 ms** con google, **1091-1159** con ollama. **La prova vera
e' la tua**, ed e' il punto 1 qui sotto. La riga da guardare e'
**`translate.attesa` contro `translate.riga`**: se tornano a coincidere,
l'anticipo non sta funzionando.

Un criterio dichiarato prima e' stato **mancato**: una sessione ollama resta al
16,4% di sfasamento contro il 10% previsto. Li' la traduzione costa 852 ms, cioe'
**piu' dell'attesa**, e l'eccedenza resta scoperta per costruzione.

**`b97f45a` — `misura_originale` si accende dalla finestra** (scheda Traduzione,
spento di serie). Il compito era una riga; sotto c'era che il campo era
dichiarato **in mezzo al commento di `font_frac`**, quindi `font_frac` — che in
quella scheda c'e' da sempre — era **senza nessuna spiegazione**. Ottava volta
del «commento orfano che si incolla al campo dopo».

**`608c177` — chi simula non scrive nel registro dell'utente.** Vedi il punto 3.

**Le schermate della guida sono pronte da guardare**: `runs\guida\`,
`scuro-guida-1..6.png` e `chiaro-guida-1..6.png` (piu' tedesco e arabo, del 18).

Restano **due decisioni tue** — il repo GitHub e il sito — **più l'exe**, che è
lavoro vero. Il link donazioni è chiuso (Ko-fi, «Buy me a token!», nel README).

**Sull'exe, perché non è spuntato**: lo spec c'è ed è aggiornato, ma l'unico
eseguibile mai costruito è del **10 agosto** — prima della finestra Menta, delle
quarantuno lingue, della guida e della rimozione delle aree. Va costruito
**quando il programma smette di cambiare**, se no si verifica un pacchetto che
domani non è più quello. E il posto in cui guardare per primo sono i **dati**:
`core/config.py` viaggia fra i dati (senza, il pannello resta senza spiegazioni)
e adesso anche `ui/lingue/*.json` — senza quelli l'exe sarebbe **solo italiano,
senza dirlo**.

## Cosa è successo il 18 agosto

**La finestra parla quarantuno lingue.** `ui.lingua` (default `auto`, segue
Windows), 41 cataloghi da 214 chiavi in `ui/lingue/*.json`, generati con
`tools/traduci_ui.py` e scritti nel repo. Cambia a caldo come il tema; arabo,
ebraico, persiano e urdu ribaltano il verso della finestra. Nessuna lingua fa
sforare le schede: la più larga è il tamil a 872 px sul minimo di 960.

**Una guida iniziale in sei passi** (`ui/tutorial.py`), il primo è la lingua.
Dove può controlla invece di chiedere fiducia.

**La scheda Sessione non è più un log**: in cima la battuta di adesso con la sua
voce e la sua fretta, poi chi ha parlato con una tessera per personaggio, il
registro sotto. E il selettore di finestra non è più illeggibile sotto il mouse
(1,12:1 → 13,95:1 sul tema scuro).

**Le aree multiple sono state tolte**, su decisione dell'utente: *infattibile*.
Girava, con le sue verifiche verdi, ma la promessa che la reggeva — più scritte
tradotte insieme sopra il gioco — dal vivo non è mantenibile, perché **l'overlay
disegna una scritta per volta**. Ne restano due pezzi: `vision.roi.troppo_grande`
e `translate.misura_originale` (il tradotto che tiene la misura dell'originale
stringendo il carattere, **spento di serie**).

**Il tetto del parlato arriva a 3×**, coi default fermi sulle misure.

## Quindi il lavoro di adesso, in ordine

> **`SESSIONI.md` è la versione operativa di questo elenco**: otto sessioni (A–H),
> una per compito, ognuna col prompt già scritto da incollare in una sessione
> nuova di Claude Code. L'ordine lì dentro non è un suggerimento — le sessioni
> F, G e H producono artefatti (immagini, exe, sito) e un artefatto generato
> prima che il programma sia fermo nasce già scaduto.

1. **Provare dal vivo col gioco acceso**, che è la cosa che manca a tutto il
   resto. Gli screenshot dicono che la finestra è quella del documento, non come
   sta **accanto a una partita**. Da guardare in particolare: la scheda Sessione
   rifatta (serve davvero mentre giochi, o distrae?), il velo al cambio di
   lingua, e la guida iniziale su una macchina che non è questa.

   ```powershell
   .\.venv\Scripts\python.exe -m tools.ui_qt --profile live
   ```

   ⚠ **senza `--no-save`**, se no la sessione non finisce in `runs/` e non si può
   rileggere con `tools/reopen`. È già successo.

2. **`translate.misura_originale`, la scelta d'occhio.** Da stanotte **si accende
   dalla finestra** (scheda Traduzione, spento di serie): non serve più `--set`.
   Va giudicato acceso, su una frase molto più lunga dell'originale: il tradotto
   sta nel riquadro ma diventa piccolo, e a un certo punto si legge peggio
   dell'originale che copre. Nessuna misura può decidere dove sta quel punto.

   *(L'HUD pronunciata è stata **chiusa senza intervento**, per decisione
   dell'utente il 18 agosto: entrambe le strade — abbassare
   `vision.continue_similarity` e la regola sul prefisso comune — costavano più
   di quanto valesse il difetto.)*

3. ~~**`! l'audio si e' fermato: OSError [Errno -9988]`**~~ — **chiuso il 19
   agosto, e non era nessuno dei due casi.** Quelle righe non le ha mai scritte
   il ciclo audio: su **122 occorrenze** nei cinque registri, **zero** vengono
   dalla catena viva. 56 le scrive `tools/scatta.py` (una stringa finta, per
   avere un guasto da fotografare) e 64 un gruppo della suite, e finivano nel
   registro dell'utente perché `Finestra.__init__` lo apre e `Finestra.scrivi`
   ci scrive. La prova è una data: il 17 agosto le venti righe cadono fra le
   18:23 e le 18:55, e le uniche quattro sessioni dal vivo di quel giorno
   partono alle **19:06**. Il controllo dall'altra parte: cinque Ferma di fila
   sul motore vero, zero messaggi `guasto`.

   Curato con `registro.banco()` — chi simula scrive in
   `livedub-banco-<data>.log`, le righe non spariscono — e la guardia del
   guasto audio è rimasta intatta, perché non era lei a sbagliare.

   **Una cosa da decidere tu**: nei registri di ieri e dei giorni prima restano
   le righe finte già scritte (35 il 16, 44 il 17, 41 il 18, 3 oggi). Non ho
   cancellato niente dal tuo disco. Se domani leggi quei file, tieni presente
   che «l'audio si è fermato» lì dentro non è mai successo davvero; e i file
   scadono da soli in sette giorni.

4. **`menta-anteprima.png` si è scollata dal prodotto**: mostra quattro schede,
   oggi sono cinque. È l'immagine che finirebbe nel README o nel sito. Si
   rigenera con `tools/scatta.py`, che fotografa la finestra vera.

5. **Cancellare la finestra Tk**, quando la Qt avrà fatto una sessione vera senza
   sorprese. Oggi resta solo per il confronto (`prova.ps1 -Tk`), non è vestita
   Menta e non è più l'entry point di niente.

## Le due decisioni ferme, che aspettano te

1. **Creare il repo GitHub.** È tutto pronto: README col diagramma, `LICENZE.md`,
   `installa.ps1`, `livedub.spec`, `livedub.bat`, il link donazioni.
   **Da decidere prima di pubblicare**: i commit fino al 17 agosto portano il
   trailer `Co-Authored-By: Claude`. Dal 18 in poi non ce ne sono più. Toglierli
   dai vecchi significa **riscrivere la storia**, e dopo la pubblicazione si
   riscriverebbe una storia già clonata: la finestra per decidere è adesso.
2. **Il sito.** hostato su github

E una decisione d'orecchio che resta da mesi: **promuovere `line_pad` a 0,2 come
default**. Misurato meglio su tutti e due i giochi, ma cambia il gioco principale
(130 → 123 battute aperte) e quello lo giudica l'ascolto.

## Come si prova quello che scrivi

```powershell
.\.venv\Scripts\python.exe -m tools.selftest                    # 1813 verifiche
.\.venv\Scripts\python.exe -m tools.selftest lingue ui_lingua tutorial
.\.venv\Scripts\python.exe -m tools.selftest menta menta_regole menta_finestra
.\.venv\Scripts\python.exe -m tools.ui_qt --profile live        # la finestra, dal vivo
.\.venv\Scripts\python.exe -m tools.scatta runs\menta          # 14 schermate, due temi
.\.venv\Scripts\python.exe -m tools.scatta runs\g --lingua de  # e in un'altra lingua
.\.venv\Scripts\python.exe -m tools.scatta runs\g --tutorial   # la guida, passo per passo
.\.venv\Scripts\python.exe -m tools.traduci_ui --controlla     # quanto manca a ogni catalogo
.\.venv\Scripts\python.exe -m tools.traduci_ui --misura        # e se qualche lingua sfora

# la catena su una registrazione, senza gioco
.\.venv\Scripts\python.exe -m tools.dub yt_scena.mp4 --profile gtav `
    --start 29 --end 315 --set vision.ocr_backend=oneocr
```

`mafia_scena.mp4` è il secondo gioco (Atto 3 «Pizzu», 150 s, gitignorato);
`assets/gioco2/` ha le due schermate che il gruppo `gioco2` usa — una su scena
chiara e una su quasi nero, cioè il caso difficile e la linea di base.

## Come voglio che tu lavori

- **Scrivi solo quando hai finito.** Non commentare ogni passo.
- **Descrivi in modo semplicissimo ma dettagliato** cosa hai fatto.
- **Non sprecare token.**
- **Prima di azzardare, chiedi.**
- **Interroga il grafo prima di grep**, e aggiornalo a fine sessione.
- **Nei commit non compare mai Claude**, in nessuna forma: niente trailer, niente
  co-autori. L'autore è sempre e solo l'utente.

## Le regole di metodo

`CLAUDE.md` le ha per esteso, e valgono più del codice. Le tre che hanno morso di
più nelle ultime sessioni:

**Controllare che la misura possa esprimere la risposta**, prima di leggere il
risultato. Un numero impossibile è più utile di uno sbagliato: quello sbagliato
si archivia.

**Un pezzo che nessuno ha guardato non è «scritto», è «supposto».** Ogni difetto
grafico è uscito da uno screenshot, non da una rilettura del codice.

**Una cura è quasi sempre più stretta del difetto.** La guardia che impediva alla
guida di aprirsi durante le verifiche copriva «costruita e dichiarata fuori
schermo» e non «costruita e mai mostrata»: la suite è rimasta appesa dieci minuti
senza stampare una riga. Non rossa — appesa. La domanda che la prende è sempre
*«cosa fa la strada vecchia che questa non fa?»*.
