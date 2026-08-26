"""Dove sta il programma, e dove tiene la roba pesante.

**Esiste per un difetto che si vede solo nell'eseguibile.** Da sorgente
`Path(__file__).parents[2] / "models"` e la cartella di lancio sono la stessa
cosa, quindi due modi diversi di dire lo stesso posto convivono per mesi senza
che niente li smentisca. Impacchettato, i `.py` finiscono in `_internal\\` e
quella formula punta a `_internal\\models`, mentre `runs\\`, `cast.json` e il
lessico restano relativi alla **cartella di lancio**: chi apre l'exe da un
collegamento riscarica cinquecento MB di modelli a ogni avvio, senza un errore e
senza capire perche'.

E c'e' un secondo prezzo, piu' silenzioso: `ui/qt_tema.py` **scrive** la spunta
e le freccine dentro `models/ui`. In `_internal\\` di un programma installato
dove Windows non lascia scrivere, quella riga solleva mentre si costruisce il
foglio di stile — cioe' la finestra non si apre, e il difetto sembra di Qt.

Quindi un posto solo che risponde: **la cartella dell'eseguibile** quando c'e' un
eseguibile, la radice del repo quando si gira da sorgente. Non la cartella di
lancio: quella cambia col collegamento che si usa, e i modelli non sono roba
della sessione, sono roba del programma.
"""

from __future__ import annotations

import sys
from pathlib import Path


def congelato() -> bool:
    """Siamo dentro un pacchetto PyInstaller?"""
    return bool(getattr(sys, "frozen", False))


def radice() -> Path:
    """La cartella del programma.

    Congelato e' quella dove sta `livedub.exe` — **non** `_internal\\`, che e' un
    dettaglio di come PyInstaller dispone i file, e **non** la cartella di
    lancio, che cambia a ogni collegamento. Da sorgente e' la radice del repo.
    """
    if congelato():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def modelli(*parti: str) -> Path:
    """`models/...` accanto al programma, che e' l'unico posto che non balla."""
    return radice().joinpath("models", *parti)


def dato(percorso: str | Path) -> Path:
    """Un percorso di configurazione, risolto contro la radice se e' relativo.

    Un percorso assoluto lo ha scritto qualcuno apposta e non si tocca. Uno
    relativo — `models/lexicon`, il default — vorrebbe dire «accanto al
    programma», ed e' quello che da sorgente sembrava gia' dire.
    """
    p = Path(percorso)
    return p if p.is_absolute() else radice() / p
