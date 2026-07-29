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
.\.venv\Scripts\python.exe -m tools.replay gameplay.mp4 --peek 8   # guardare la ROI
.\.venv\Scripts\python.exe -m tools.calibrate gameplay.mp4 --write profiles\gtav.json
.\.venv\Scripts\python.exe -m tools.replay gameplay.mp4 --profile gtav --start 60 --end 120
.\.venv\Scripts\python.exe -m tools.bench_speaker --clean                 # solo la risposta nota
.\.venv\Scripts\python.exe -m tools.bench_speaker gameplay.mp4 --profile gtav --audio-only --start 300 --end 900
```

`bench_speaker --audio-only` salta l'OCR, che costa **piu' del tempo reale**:
420 s di video sono ~10 minuti di passata completa e ~40 secondi di sola
traccia audio. La curva non ha bisogno dei sottotitoli; l'analisi del grigio
si'.

**Su una registrazione nuova si guarda prima e si misura dopo.** `--peek` salva
i ritagli della ROI cosi' come la pipeline li vede, e costa dieci secondi. La
ROI di default inquadrava il tappeto: l'OCR restituiva zero battute, che e'
indistinguibile da "il modello non regge". La ROI si e' anche rivelata **del
setup di cattura e non del gioco** — stesso gioco e stessa risoluzione, i
sottotitoli stanno a 0,965 dell'altezza in una registrazione e a 0,914
nell'altra — quindi `tools/calibrate.py` va rifatto a ogni cambio di cattura,
non una volta per gioco.

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

**Guardare l'ingresso del modello prima di accusare il modello**, che e' la
stessa regola in un altro travestimento e ha gia' pagato due volte. L'OCR
leggeva `Oaai recuperiamo veicoli acauistati`, e sembrava un riconoscitore
scadente sull'italiano. Il ritaglio che riceveva aveva le code di `g` e `q`
tagliate via — e una `g` senza coda **e'** una `a`. Il modello rispondeva
benissimo a una domanda diversa. Salvare il ritaglio su disco e guardarlo costa
dieci secondi e chiude la questione; ragionare sul perche' il modello sbagli
non la chiude mai, perche' il modello non sta sbagliando.

**Guardare ogni lettura, non solo quelle che arrivano in fondo.** Le letture
della stessa battuta sembravano rumore casuale viste dall'uscita della
pipeline. Elencandole tutte erano stabilissime — e stabilmente sbagliate sulle
stesse lettere. "Instabile" e "sistematicamente sbagliato" hanno rimedi
opposti: nel primo caso si vota fra le letture, nel secondo votare consolida
l'errore.

**Controllare che la misura possa esprimere la risposta** prima di credere a
quello che dice. Due esempi presi in flagrante mentre si calibrava il video, e
sono la stessa forma di errore in due travestimenti:

- selezionare i pixel di testo con una maschera che pretende uno **stacco dal
  fondo maggiore di 60**, e poi misurare lo stacco dei pixel di testo. Risposta:
  60,15. Non era il valore del testo, era la soglia che si guardava allo
  specchio;
- selezionare i pixel di testo su "quasi bianco e acromatico" e misurare la
  stessa cosa. Risposta: **−2,3**. Dentro la ROI ci sono muri chiari e
  carrozzerie bianche, bianchi e acromatici quanto un glifo.

Quello che distingue un glifo non e' quanto e' chiaro ma che e' **sottile**, e
serve un operatore diverso da quello della pipeline (top-hat morfologico contro
sottrazione di media) perche' selezionare con uno e misurare con l'altro sia una
misura e non un'eco.

**Il caso nullo migliore condivide tutto tranne la risposta.** Un embedding di
speaker sull'audio del gioco dava EER 27% e sembrava un riconoscitore debole. Lo
stesso identico protocollo sui **lati** del segnale stereo — dove il dialogo per
costruzione non c'e' — dava 25,0% dove il centro dava 25,0. Non era un
riconoscitore debole: non stava riconoscendo niente, stava misurando quanto due
ritagli fossero vicini nel tempo. Il silenzio e il backend stupido dicevano la
stessa cosa, ma i lati la dicono meglio perche' sono *simultanei* al parlato:
stessa scena, stesso istante, stessa energia che entra ed esce. Un caso nullo
preso in un altro momento lascia sempre aperta l'obiezione "li' era diverso".

**Un si'/no diventa una diagnosi aggiungendo il gradino di mezzo.** "Le voci
pulite si separano, quelle del gioco no" ha quattro spiegazioni possibili e un
solo numero. Sommare le *stesse* voci pulite al fondo *vero* della registrazione,
a rapporti segnale/rumore decrescenti, ne lascia in piedi una sola: da 0% di EER
a +24 dB si scende a 18% a 0 dB, e il gioco — che stacca dal fondo di +3 dB —
cade esattamente li'. Il colpevole non e' il modello, e' quello che gli si da'.

**Una statistica robusta invece del minimo.** Prendere il minimo fra i frame
significa lasciar decidere al frame peggiore: un solo frame con un muro bianco
nella ROI portava `contrast_min` da 40 a 20. Il decimo percentile risponde alla
stessa domanda senza farsi sequestrare da un caso.

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
