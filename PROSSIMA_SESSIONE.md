# Prompt per la prossima sessione

Copia da qui in giù.

---

Lavoro su **livedub** (`C:\Users\filde\Documents\!code\CLAUDE\livedub`),
doppiaggio italiano dal vivo dei sottotitoli dei videogiochi.

## La prima cosa: il grafo è la memoria

In `graphify-out/graph.json` c'è la mappa della codebase. Per **qualunque**
domanda architetturale — dove sta X, cosa rompo se tocco Y, chi chiama cosa — si
interroga quello **prima** di partire a grep:

```
graphify query "<domanda>"
```

Costruirlo è caro, interrogarlo no. **È stato aggiornato a fine sessione il 17
agosto**, quindi conosce già tutto quello che è stato scritto fino a qui: il
tema Menta (`ui/qt_tema.py` con `R(h)`, `contrasto`, `delta_e`, `carattere_log`),
la finestra rifatta (`tools/ui_qt.py`), `tools/scatta.py`, le regole fuori dalle
finestre (`core.motore.gravita`, `barra_misura`, `Misura`), `SpokenLine.roi` e
`.muta`, `DubPipeline._mostra`, `SubtitleReader.roi` e
`vision.aree.troppo_grande`.

Si riaggiorna con `/graphify . --update` **dopo** modifiche grosse, non prima di
ogni task.

## Le cento domande: finite

`DOMANDE_PRODUZIONE.md` è chiuso. **84 chiuse, 16 dichiarate come limite noto,
zero senza risposta.** Un ❓ non è un ✅ in attesa, ed è per questo che nessuna è
rimasta tale: ognuna ha o una correzione, o una misura, o un limite scritto col
suo perché.

**`METODO_DOMANDE.md` dice come sono state lavorate** — sei passi, una per volta,
cinque sotto-domande scritte *prima* di guardare il codice, la soglia dichiarata
*prima* di vedere il numero. È il file da leggere se ne arrivano di nuove.

I sei difetti veri trovati chiudendole, che sono la ragione per cui l'esercizio
si fa:

| | cosa |
|---|---|
| 92 | la memoria cresceva senza limite: 3600 battute → 3600 oggetti mai liberati |
| 50, 91 | `Session` teneva **660 MB** di audio in RAM, e non lo diceva niente |
| 50 | `ui.save_mix` dichiarato e **mai letto da nessuno** — il quinto campo così |
| 39 | il thread audio moriva **in silenzio** con le cuffie staccate |
| 32 | due sessioni nello stesso secondo scrivevano nella **stessa cartella** |
| 27, 28 | `capture.fps = -5` e `decide_after_ms = 99999` passavano senza un fiato |

Nessuno si vedeva leggendo il codice. Cinque su sei sono usciti da una misura.

**E poi le cure sono state rilette, il 11 agosto: cinque erano metà.** Non i
difetti — le *correzioni* dei difetti, tutte consegnate con la suite verde:

| | cosa non funzionava davvero |
|---|---|
| 15, 16 | `profiles/ultima.json` scritto uscendo e **mai riletto aprendo** |
| 39 | il guasto dell'audio lasciava **Avvia spento**, la sessione aperta, lo stato **verde** |
| 50 | con `save_mix=false` ogni `t_wav` era **nullo**: `tools/reopen <secondo>` cieco |
| 92 | il tetto era su `spoken` e non su `closed` |
| 81 | il gestore globale **non vedeva i thread**, cioè dove vive la catena |

Quattro su cinque stanno nella finestra Qt o al suo confine, che è l'unica parte
del programma **senza nessuna verifica**. Adesso la parte provabile senza aprire
Qt sta fuori da Qt (`core.preferenze.riprendi`, `core.motore.colore_stato`, e
adesso anche `gravita`, `barra_misura` e tutto `ui/qt_tema.py`).

## E la catena è stata provata dal vivo, davvero

L'11 agosto, con il gioco sostituito da una registrazione a schermo intero in
Chrome: cattura dello schermo vera, OCR vero, audio vero da Voicemeeter, voce nelle
casse. **La catena regge e i numeri sono quelli dichiarati** — latenza p50
**665 ms** (dichiarato ~670), `mix.underrun` **0**, e `dub.rate_x1000` al p50
**1000**, cioè il numero che `DA_VERIFICARE.md` chiedeva di guardare: si è
staccato da 1250 e la diagnosi su `accepted_delay_ms` era giusta.

Quello che la prova ha trovato, e che i banchi non avevano visto:

| | cosa |
|---|---|
| **HUD pronunciata** | «Sali sul \[tasto]» sta nella fascia dei sottotitoli, il glifo cambia a ogni fotogramma e apre una battuta nuova: **8 su 17 dal vivo, 11 su 46 sul banco**. Aperto |
| `--output` | non poteva funzionare: cercava fra i loopback. Corretto |
| cattura | lo schermo intero costava **32,4 ms** su 33 di budget. Adesso si prende solo la fascia: **+35% di letture, +5 sottotitoli**. Fatto |
| `tools/live.py` | non scriveva `speaker.jsonl`, cioè proprio il file che serve a rispondere. Corretto |

**Due conclusioni sbagliate sono state ritirate**, e vale la pena sapere come:
avevo scritto «dal vivo si perde il 60% delle righe» e «riconosce molto peggio
del banco». Falso tutte e due — confrontavo **tratti diversi della stessa scena**
(una volta il video era perfino finito a metà prova). Allineando i tratti: 31
battute contro 33, e voce neutra 81% contro 78%.

**Le 16 dichiarate non sono lavoro dimenticato.** Sei si sono chiuse insieme con
Avvia nella finestra Qt e con la barra della misura: l'indicatore di latenza,
l'underrun a schermo e il selettore d'area col mouse ci sono. Le altre sono limiti veri
— testo scuro su fondo chiaro, sottotitoli in fumetti, lingue non latine, Python
dello Store — e stanno nel README.

## Quindi il lavoro di adesso, in ordine

1. **Provare Menta e le aree dal vivo, col gioco acceso.** È la cosa che manca a
   tutto il resto: gli screenshot dicono che la finestra è quella del documento,
   ma non possono dire come sta **accanto a una partita** — se i numeri della
   barra in fondo distraggono, se l'alone sulla spia serve, se il log senza
   monospazio si legge ancora a colpo d'occhio. E le tre correzioni sulle aree
   (§ sotto) sono verificate sul banco e **mai viste a schermo**: una zona muta
   tirata su un cartello di missione, con `translate.enabled=true`, è la prova.

   ```powershell
   .\.venv\Scripts\python.exe -m tools.ui_qt --profile live
   ```

   ⚠ **senza `--no-save`**, se no la sessione non finisce in `runs/` e non si può
   rileggere con `tools/reopen`. È già successo.

2. **Il carattere del log: una decisione d'occhio, non di codice.** Era
   monospazio, ora è quello dell'interfaccia con le **cifre tabulari** e i campi
   separati dai punti (`12.4s · M1 · it_riccardo · 620 ms · testo`). Le colonne
   rigide sono tornabili in una riga (`tema.carattere_log`), e la domanda è solo
   se scandirlo mentre si gioca funziona ancora.

3. **L'HUD pronunciata**, l'unico difetto vero lasciato aperto dalla prova dal
   vivo dell'11 agosto, e aspetta una decisione fra due strade perché una tocca
   una soglia che vale per tutti i sottotitoli. La misura è già fatta: le letture
   consecutive di `Sali sul <spazzatura>` si somigliano fra **0,58 e 0,77** e
   `vision.continue_similarity` vale 0,75, quindi dieci su dodici aprono una
   battuta nuova invece di continuare quella di prima. L'altra strada è una
   regola sul **prefisso comune**, che non tocca il caso generale. Da chiedere
   prima di toccare.

4. **Cancellare la finestra Tk**, quando la Qt avrà fatto una sessione vera senza
   sorprese. Oggi resta solo per il confronto (`prova.ps1 -Tk`), non è vestita
   Menta e non è più l'entry point di niente.

## Cosa è successo il 17 agosto

**La finestra è Menta**, costruita da `docs/interfaccia.md`. Il riassunto di cosa
conta è in `CLAUDE.md`, sezione «La finestra: Menta» — inclusa la sottosezione
**«Quello che il documento diceva e che a schermo era sbagliato»**, che è la
parte da leggere prima di toccare l'interfaccia: cinque prescrizioni del disegno
sono cadute alla prima occhiata dell'utente, e nessuna dava errore.

**E tre difetti sulle aree**, che tenevano ferma una funzione intera: aggiungere
una zona «solo testo» non faceva niente.

| | cosa | come si è visto |
|---|---|---|
| 1 | una sola area **perdeva il rettangolo** e leggeva la vecchia ROI | il lettore era su `(0.15,0.72,...)` invece che sull'area |
| 2 | le battute mute non erano **tradotte né disegnate** | traduttore finto: 2 sottotitoli aperti, 1 battuta uscita |
| 3 | un'area grande **non legge** | a schermo intero: 14 fotogrammi, 14 saltati, 0 letture |

Il terzo è un **limite dichiarato**, non un difetto: la frazione di pixel
cambiati ha l'area al denominatore, quindi `troppo_grande()` lo dice sopra 0,30.
Tradurre tutto lo schermo è un altro prodotto.

**E la cura del primo si era mangiata trentuno manopole calde** — passava una
copia di `cfg.vision` a ogni lettore. È la lezione della sessione, ed è già in
`CLAUDE.md`: *una cura che copia un oggetto condiviso rompe tutto ciò che
contava sul fatto che fosse condiviso*, e la domanda che la prende è «cosa faceva
prima che adesso non fa più?».

## Dove siamo

Suite verde a **1678 verifiche**. `SviluppoProgetto.md`: **16 step su 19**.

**La finestra è quella Qt, ed è vestita Menta.** `tools/ui_qt.py` (PySide6, il
binding ufficiale di The Qt Company, LGPL-3 e quindi compatibile con la nostra
GPL-3) è **il prodotto**: è quella che impacchetta `livedub.spec`, quella che
apre `livedub.bat`, quella che lancia `tools/prova.ps1`. La Tk (`tools/ui.py`)
resta raggiungibile con `prova.ps1 -Tk` per il confronto, e non verrà vestita.

Il disegno è `docs/interfaccia.md`; i suoi numeri stanno in `ui/qt_tema.py`, che
è la sua traduzione in codice — **si cerca lì e non si inventa**. Il riassunto di
cosa conta è in `CLAUDE.md`, sezione «La finestra: Menta».

Cosa c'è nella finestra:

- i due cicli **fuori da qualunque finestra** (`core/motore.py`), Avvia e Ferma,
  l'overlay, il selettore d'area col mouse e quello di finestra;
- **sei schede** (Preparazione, Sessione, Voce, Traduzione, Aree, Tutte le
  impostazioni) e **tre livelli di utente** — l'essenziale (10 parametri), le
  principali (33), tutto (166);
- le impostazioni **generate percorrendo l'albero** (`core/schema.py`), con il
  ⓘ che apre il commento di `core/config.py` così com'è scritto, misure comprese;
- **il tema segue Windows** (chiaro/scuro) e cambia in diretta, con due tavolozze
  che non sono l'una l'inverso dell'altra;
- il **pannello dei tre passi** al posto della riga di log che spariva sotto la
  prima decina di messaggi; la **pillola di stato** col logo che cambia faccia
  sulla stessa regola; le **marche di gravità** nel margine del log; la
  **tessera del guasto col bottone dentro**; la **barra della misura** a 2 Hz;
- la striscia **«Applica ora»** per i parametri che si leggono solo all'avvio;
- versione (F1), diagnostica negli appunti (Ctrl+L), profili (Ctrl+S / Ctrl+O),
  geometria ricordata, registro su file, dialogo del crash.

**Come si guarda senza aprire il gioco.** Si costruisce la finestra con
`WA_DontShowOnScreen`, si forza `tema.attuale` alla tavolozza voluta e si chiama
`grab()`: due temi, sei schede, trenta secondi. **Non con
`QT_QPA_PLATFORM=offscreen`**, che ha *zero* caratteri installati e restituisce
una finestra di quadratini — cioè una fotografia che non può mostrare il difetto
che si sta cercando.

## Le due decisioni ferme, che aspettano te

1. **Creare il repo GitHub** — hai detto «aspetta». È tutto pronto: README col
   diagramma, `LICENZE.md`, `installa.ps1`, `livedub.spec`, `livedub.bat`.
   **Da decidere prima di pubblicare**: 167 commit su 170 hanno il trailer
   `Co-Authored-By: Claude`. L'autore git sei sempre e solo tu, quindi su GitHub
   non comparirebbe nessun collaboratore, ma la riga si legge nei messaggi.
   Toglierla significa riscrivere la storia.
2. **Il link donazioni** — hai detto «dopo».

E una decisione d'orecchio: **promuovere `line_pad` a 0,2 come default**.
Misurato meglio su tutti e due i giochi, ma cambia il gioco principale (130 → 123
battute aperte) e quello lo giudica l'ascolto. Basta una prova con
`tools/dub.py --mp4` affiancata.

## Come si prova quello che scrivi

```powershell
.\.venv\Scripts\python.exe -m tools.selftest                    # 1678 verifiche
.\.venv\Scripts\python.exe -m tools.selftest menta menta_regole menta_finestra
.\.venv\Scripts\python.exe -m tools.selftest area_sola aree_muta area_grande
.\.venv\Scripts\python.exe -m tools.ui_qt --profile live        # la finestra, dal vivo
.\.venv\Scripts\python.exe -m tools.scatta runs\menta          # 14 schermate, due temi
.\.venv\Scripts\python.exe -m tools.bench_memoria --battute 3600

# la catena su una registrazione, senza gioco
.\.venv\Scripts\python.exe -m tools.dub yt_scena.mp4 --profile gtav `
    --start 29 --end 315 --set vision.ocr_backend=oneocr
```

`mafia_scena.mp4` è il secondo gioco (Atto 3 «Pizzu», 150 s, gitignorato);
`assets/gioco2/` ha le due schermate che il gruppo `gioco2` usa.

## Come voglio che tu lavori

- **Scrivi solo quando hai finito.** Non commentare ogni passo.
- **Descrivi in modo semplicissimo ma dettagliato** cosa hai fatto.
- **Non sprecare token.**
- **Prima di azzardare, chiedi.**
- **Interroga il grafo prima di grep**, e aggiornalo a fine sessione.

## Le regole di metodo

`CLAUDE.md` le ha per esteso, e valgono più del codice. Le due che hanno morso
più spesso in questa sessione:

**Controllare che la misura possa esprimere la risposta**, prima di leggere il
risultato. Un numero impossibile è più utile di uno sbagliato: quello sbagliato
si archivia.

**Un pezzo che nessuno ha guardato non è «scritto», è «supposto».** Ogni difetto
grafico di questa sessione — la spunta che era un quadrato, le frecce che erano
quadratini, il contatore schiacciato, `line_pad` che spiegava un altro campo — è
uscito da uno screenshot, non da una rilettura del codice.

Fine del prompt.
