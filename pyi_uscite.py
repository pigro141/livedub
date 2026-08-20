"""Le uscite standard, quando il programma e' un eseguibile senza console.

Non e' un modulo del programma: e' un **gancio d'avvio** di PyInstaller, elencato
in `runtime_hooks` dentro `livedub.spec`, e gira prima di `tools/ui_qt.py`.

## Il difetto, misurato

`livedub.spec` costruisce con `console=False`, perche' il prodotto e' una
finestra e non un terminale. Su Windows quel modo lascia il processo **senza
handle standard**, e Python mette `sys.stdout` e `sys.stderr` a `None`. Da quel
momento *qualunque* `print` fuori dal nostro codice — cioe' quello delle
librerie, che non possiamo cambiare — solleva
`AttributeError: 'NoneType' object has no attribute 'write'`.

E non e' teoria. Aperto il pacchetto del 20 agosto e premuto **«Misura questo PC
e scarica quello che manca»**, il banco ha risposto con sette righe uguali:

    il modello della voce migliore non e' arrivato: resta la voce leggera
    il riconoscimento di chi parla: non riuscito — AttributeError: 'NoneType'
        object has no attribute 'write'
    il modello della voce: non riuscito — AttributeError: ...
    gli stili di voce: non riuscito — AttributeError: ...
    le due voci italiane: non riuscito — AttributeError: ...

La barra di avanzamento di `huggingface_hub` scrive su `sys.stderr`. Quindi
nell'eseguibile **nessun modello si poteva scaricare**: non Piper, non Kokoro,
non ECAPA — e il pacchetto e' costruito apposta per scaricarli al primo avvio,
che e' una scelta di licenza scritta in `LICENZE.md`. Il programma partiva,
mostrava la finestra giusta, dichiarava per bene cosa mancava, e non poteva
rimediare a niente di cio' che dichiarava.

## Perche' non `os.devnull`

Buttare via quelle scritture zittirebbe anche le dichiarazioni che questo
progetto ha pagato due volte per avere: `core.onnx.provider_voluti` che dice «si
ripiega sulla CPU», `verifica_provider` che dice «chiesto CUDA, ottenuto CPU»,
il worker di OneOCR che dice perche' non e' partito. Sono tutte su `stderr`, e
sono precisamente il contrario del ripiego silenzioso.

Quindi vanno **nel registro**, che gia' esiste per questo motivo — `core/
registro.py` comincia con «con l'eseguibile non c'e' nemmeno una console dove
guardare» — e che l'utente apre dal bottone «Apri il registro».

## Le due cose che questo gancio non fa, e sono volute

Non tocca `sys.stdout`/`sys.stderr` se **non** sono `None`. Da sorgente non
cambia niente, e soprattutto non cambia niente nel **processo figlio di
OneOCR**: quello nasce con `stderr=PIPE`, il suo `stderr` e' vero, e ci passa il
protocollo (`ONEOCR-PRONTO`). Dirottarlo nel registro vorrebbe dire che il
genitore aspetta per sempre una riga che non arriva piu'.

Non apre il registro. Lo apre `tools/ui_qt.py` quando parte, come ha sempre
fatto: aprirlo qui vorrebbe dire due punti che decidono la stessa cosa, e il
secondo e' quello che nessuno aggiorna.
"""

from __future__ import annotations

import sys


class _AlRegistro:
    """Un oggetto che sa solo `write` e `flush`, e li porta nel registro.

    Si accumula fino all'a-capo perche' chi stampa una barra di avanzamento
    scrive un pezzo per volta: senza, ogni frammento diventerebbe una riga con
    la sua ora, e il registro sarebbe illeggibile proprio nel momento in cui
    serve.
    """

    def __init__(self, canale: str) -> None:
        self._canale = canale
        self._pezzi: list[str] = []

    def write(self, testo) -> int:
        testo = str(testo)
        self._pezzi.append(testo)
        if "\n" in testo or "\r" in testo:
            self.flush()
        return len(testo)

    def flush(self) -> None:
        intero, self._pezzi = "".join(self._pezzi), []
        # `\r` e' l'a-capo delle barre di avanzamento: si tiene l'ultimo stato e
        # non i duecento intermedi.
        riga = intero.replace("\r", "\n").strip()
        if not riga:
            return
        try:
            from core import registro

            for r in riga.splitlines():
                registro.scrivi(f"{self._canale}: {r}")
        except Exception:
            pass

    def isatty(self) -> bool:
        # Chi chiede se sta parlando a un terminale lo chiede per decidere se
        # disegnare una barra: dire di no fa scrivere una riga per volta, che e'
        # quello che un file di registro puo' contenere.
        return False

    def fileno(self) -> int:
        # Chi vuole il descrittore vero deve sentirsi dire che non c'e'. Un
        # numero inventato lo farebbe scrivere **da un'altra parte**.
        raise OSError("uscita senza descrittore: siamo nel registro")

    # Le librerie danno per scontato un file di testo: meglio rispondere che
    # sollevare da un posto lontano dal difetto.
    encoding = "utf-8"
    errors = "replace"

    def writable(self) -> bool:
        return True

    def readable(self) -> bool:
        return False

    def seekable(self) -> bool:
        return False

    def close(self) -> None:
        self.flush()


if sys.stdout is None:
    sys.stdout = _AlRegistro("stdout")
if sys.stderr is None:
    sys.stderr = _AlRegistro("stderr")
