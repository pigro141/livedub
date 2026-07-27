# CLAUDE.md — livedub

Guida per Claude Code su questo repo. Leggere prima di toccare qualsiasi cosa.

## Cos'e'

Doppiaggio italiano live dei sottotitoli di un videogioco. Vedi `README.md` per
l'architettura e la grammatica dei sottotitoli, che e' la fondamenta di tutto.

## Le due cartelle sorelle non si guardano

`..\gta-redub-live` e `..\gta-redub-v2` sono **bozze fallite**, dichiarate tali
dall'utente. Non si leggono, non si copiano, non si citano le loro misure. Se
serve una logica che li' esisteva, si riscrive e si rimisura qui.

## Comandi

```powershell
.\.venv\Scripts\python.exe -m tools.selftest              # tutta la suite
.\.venv\Scripts\python.exe -m tools.selftest ring config  # gruppi scelti
.\.venv\Scripts\python.exe -m tools.selftest -v           # con i verdi in chiaro
.\.venv\Scripts\python.exe -m tools.replay --demo --determinism
.\.venv\Scripts\python.exe main.py --dump-config
```

- venv: `.venv` (Python 3.11.9), sempre invocato per esteso.
- **Non c'e' pytest.** La suite e' `tools/selftest.py`; un gruppo si esegue anche
  da codice: `from tools.selftest import test_ring, Check; c=Check(); test_ring(c); c.report()`.
- Un gruppo nuovo si aggiunge al dizionario `GROUPS` in fondo al file.

## Regole che il codice gia' applica

**Due tempi, mai uno.** `Stage.clock` e' il tempo del *media* (virtualizzabile,
serve a timbrare gli eventi); il *costo* si misura sempre a muro con
`perf_counter`. Confonderli fa risultare gratis ogni stadio durante il replay —
la misura non diventa imprecisa, diventa incapace di esprimere la risposta. Il
primo tentativo aveva questo bug; le verifiche in `test_stage` esistono per
impedirne il ritorno.

**Ogni stadio si cronometra da solo e si puo' spegnere** (`core/stage.py`). Il
modo piu' rapido di scoprire chi costa e' togliergli la corrente e rimisurare.

**Verificare una trasformata contro la propria inversa** prima di accusare un
modello. Una trasformata sbagliata produce spazzatura plausibile, non un errore.
Vale per lo stretch WSOLA (stretch di `r` poi `1/r` deve restituire l'ingresso) e
per il classificatore di righe (frame sintetici con colori noti prima di un
frame vero).

**Controllare che la misura possa esprimere la risposta** prima di credere a
quello che dice.

## Config

Un solo albero di dataclass in `core/config.py`, ogni campo raggiungibile con
`--set sezione.campo=valore`. Un percorso inesistente e' un errore all'avvio, non
un refuso silenzioso. I default sono **punti di partenza dichiarati, non misure**:
ROI, soglie di colore e coefficienti di durata vanno ricavati con
`tools/calibrate.py` e scritti in `profiles/<gioco>.json`.

## Convenzioni

- **Codice in italiano**: commenti, docstring, messaggi di log, help della CLI,
  stringhe dell'interfaccia. **Identificatori in inglese.**
- Windows + PowerShell.
- I messaggi git multi-riga da PowerShell si rompono (le here-string vengono
  ri-analizzate e si mangiano le virgolette): scrivere il messaggio su file e
  usare `git commit -F file`.
- Commit solo dopo una suite verde. Commit piccoli e logici. Solo in locale.
- `models/`, `runs/` e le registrazioni sono materiale della macchina: gitignorati.

## Dove sta il lavoro

Il piano con le fasi F0→F6, le tecnologie scelte e i rischi con la misura che li
scioglie: `C:\Users\filde\.claude\plans\progetto-so-che-ci-fancy-rossum.md`.
