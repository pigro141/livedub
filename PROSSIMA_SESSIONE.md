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

## Il lavoro di adesso: finire le cento domande

`DOMANDE_PRODUZIONE.md` è l'elenco delle domande che si fanno a un programma
prima di darlo a qualcuno che non l'ha scritto. Stato: **44 a posto, 34 difetti,
20 mai provate, 2 mezze**.

**`METODO_DOMANDE.md` dice come si lavorano**, ed è la cosa da leggere prima di
toccarne una: sei passi, una domanda per volta, cinque sotto-domande scritte
*prima* di guardare il codice, la soglia dichiarata *prima* di vedere il numero.

Non è burocrazia: ognuno dei sei passi esiste perché saltandolo si è già
sbagliato. In questa sessione, tre volte.

Le rimanenti si dividono in tre gruppi, e l'ordine consigliato è **primo, terzo,
secondo**:

| gruppo | quante | esempi |
|---|---|---|
| si chiudono da soli | ~20 | intervalli dei valori (27, 28), ricerca nel log (25), annulla (31), `runs/` che cresce (85), indicatore di latenza (44, 70, 86) |
| sono lavoro vero | ~6 | il WAV scritto a blocchi invece che in RAM (84, 91), selettore d'area nella Qt (37), portare **Avvia** nella finestra Qt |
| servono te e il gioco acceso | ~8 | cuffie staccate a metà (39), fps rubati (93), schermo a 150% (12), due monitor (55) |

Il secondo gruppo si accorpa alla prossima prova d'ascolto dell'utente, che è
l'unico momento in cui il gioco è acceso comunque.

## Dove siamo

Suite verde a **1368 verifiche**. `SviluppoProgetto.md`: **16 step su 19**.

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
   **Da decidere prima di pubblicare**: 156 commit su 165 hanno il trailer
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
.\.venv\Scripts\python.exe -m tools.selftest                    # 1368 verifiche
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
