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

Costruirlo è caro, interrogarlo no. Si aggiorna con `/graphify . --update` dopo
modifiche grosse — e l'8-11 agosto ne sono state fatte parecchie (front-end Qt,
`core/schema.py`, `vision/aree.py`, `core/preferenze.py`, `core/registro.py`,
`core/versione.py`), quindi **il primo comando della sessione è
`/graphify . --update`** se non risulta già fatto.

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
Qt sta fuori da Qt (`core.preferenze.riprendi`, `tools.ui.colore_stato`).

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

**Le 16 dichiarate non sono lavoro dimenticato.** Sei si chiudono tutte insieme
**quando Avvia arriverà nella finestra Qt** (l'indicatore di latenza, l'underrun
a schermo, il selettore d'area col mouse): un indicatore vivo in una finestra che
non fa girare la catena non avrebbe niente da mostrare. Le altre sono limiti veri
— testo scuro su fondo chiaro, sottotitoli in fumetti, lingue non latine, Python
dello Store — e stanno nel README.

## Quindi il lavoro di adesso è uno solo

**Portare Avvia nella finestra Qt**, con l'overlay. È il pezzo su cui questo
progetto ha trovato i difetti peggiori (il programma che leggeva se stesso, la
finestra dimensionata sul testo sbagliato), quindi va portato con le stesse
verifiche, non di fretta. Chiude sei domande e rende la finestra Tk cancellabile.

## Dove siamo

Suite verde a **1403 verifiche**. `SviluppoProgetto.md`: **16 step su 19**.

**La finestra è stata rifatta in Qt** (`tools/ui_qt.py`, PySide6, che è il
binding ufficiale di The Qt Company ed è LGPL-3, compatibile con la nostra
GPL-3). Perché si è cambiato motore: in Tkinter gli angoli stondati sono costati
tre giri di prove a schermo — sostituendo il bordo di un bottone spariva la
scritta, riscrivendo il layout di un contatore il numero si schiacciava — e in Qt
sono `border-radius: 8px`.

Cosa c'è nella finestra Qt:

- quattro schede (Sessione, Tecnologie, Aree, Impostazioni avanzate);
- **tre livelli di utente** — l'essenziale (10 parametri), le principali (33),
  tutto (166) — perché 166 manopole uguali sono la risposta giusta a una domanda
  che quasi nessuno fa;
- le impostazioni **generate percorrendo l'albero** (`core/schema.py`), con il
  `?` che apre il commento di `core/config.py` così com'è scritto, misure
  comprese;
- **il tema segue Windows** (chiaro/scuro) e cambia in diretta, con sei colori
  dei personaggi rifatti per il chiaro;
- la striscia **«Applica ora»** per i parametri che si leggono solo all'avvio;
- versione (F1), diagnostica negli appunti (Ctrl+L), profili (Ctrl+S / Ctrl+O),
  geometria ricordata, registro su file, gestore globale delle eccezioni.

**Ma il bottone Avvia non è ancora portato.** I due cicli — audio a 10 ms e video
a 30 Hz — vivono in `tools/ui.py` intrecciati con l'overlay, che è ancora Tk.
**Per doppiare dal vivo si usa ancora `python -m tools.ui`**, e la finestra Qt lo
scrive nel log invece di offrire un bottone che non fa niente. Le due convivono
di proposito finché la seconda non è pari: riscrivere dentro quella che funziona
era il modo più rapido di restare senza nessuna delle due.

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
.\.venv\Scripts\python.exe -m tools.selftest                    # 1403 verifiche
.\.venv\Scripts\python.exe -m tools.ui_qt --profile gtav        # la finestra nuova
.\.venv\Scripts\python.exe -m tools.ui --profile live           # il dal vivo, ancora Tk
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
