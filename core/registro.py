"""Il registro su file, perche' un guasto non muoia con la finestra.

**Perche' esiste.** Se qualcosa esplode, l'utente vede una finestra che si chiude
e basta: con l'eseguibile non c'e' nemmeno una console dove guardare. Sono le
domande 81-83 di `DOMANDE_PRODUZIONE.md`, e sono tre facce della stessa cosa —
un difetto che non lascia traccia e' un difetto che non si corregge.

**Cosa ci finisce**: la scheda della versione all'apertura (senza, il registro
non dice quale codice stava girando), ogni riga che va anche nel log a schermo, e
qualunque eccezione non gestita **con il suo traceback**.

**Dove**: `%LOCALAPPDATA%\\livedub\\log\\`, un file per giorno, e si tengono gli
ultimi sette. Non in `runs/`, che e' materiale delle prove: un guasto succede
anche prima che una sessione cominci.
"""

from __future__ import annotations

import datetime as _dt
import sys
import traceback
from pathlib import Path

from core.preferenze import cartella
from core.versione import scheda

_APERTO = None
GIORNI = 7


def _cartella() -> Path:
    c = cartella() / "log"
    c.mkdir(parents=True, exist_ok=True)
    return c


def apri() -> None:
    """Apre il registro di oggi e ci scrive la scheda della versione."""
    global _APERTO
    if _APERTO is not None:
        return
    try:
        oggi = _dt.date.today().isoformat()
        _APERTO = (_cartella() / f"livedub-{oggi}.log").open("a", encoding="utf-8")
        scrivi("=" * 60)
        scrivi(scheda())
        _pulisci()
    except Exception:
        _APERTO = None


def scrivi(testo: str) -> None:
    if _APERTO is None:
        return
    try:
        ora = _dt.datetime.now().strftime("%H:%M:%S")
        for riga in str(testo).splitlines() or [""]:
            _APERTO.write(f"{ora}  {riga}\n")
        _APERTO.flush()
    except Exception:
        pass


def _pulisci() -> None:
    """Si tengono gli ultimi sette giorni: un registro che cresce per sempre e'
    un altro modo di riempire il disco di qualcun altro."""
    try:
        file = sorted(_cartella().glob("livedub-*.log"))
        for vecchio in file[:-GIORNI]:
            vecchio.unlink(missing_ok=True)
    except Exception:
        pass


def cattura_eccezioni(al_guasto=None) -> None:
    """Installa il gestore globale: **niente esce di scena in silenzio**.

    Senza, un'eccezione dentro un callback di Qt stampa su una console che
    nell'eseguibile non esiste, e la finestra resta li' come se niente fosse —
    che e' peggio di un crash, perche' l'utente continua a usarla credendo che
    funzioni.
    """
    precedente = sys.excepthook

    def mio(tipo, valore, tb) -> None:
        testo = "".join(traceback.format_exception(tipo, valore, tb))
        scrivi("GUASTO NON GESTITO\n" + testo)
        if al_guasto is not None:
            try:
                al_guasto(tipo, valore, testo)
            except Exception:
                pass
        precedente(tipo, valore, tb)

    sys.excepthook = mio


def percorso() -> Path:
    return _cartella()
