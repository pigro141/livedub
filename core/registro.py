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

**E chi simula scrive in un altro file, che e' la cura di un difetto misurato.**
Il canale del registro e' `Finestra.scrivi`, e la finestra la costruiscono anche
`tools/scatta.py`, `tools/traduci_ui.py` e due gruppi della suite: tutto quello
che scrivono per **avere qualcosa da fotografare o da controllare** finiva nel
registro dell'utente, indistinguibile da cio' che e' successo davvero. Contate
al 19 agosto 2026: **122 righe «l'audio si e' fermato» e zero vere** — 56 dalle
schermate (`OSError: [Errno -9988] Stream closed`, una stringa scritta a mano) e
64 dalla suite, sparse fra sessioni dal vivo autentiche. Sono costate una
sessione intera di indagine su un guasto che non e' mai esistito, ed erano
esattamente il difetto che questo file esiste per **non** avere: un registro che
non risponde piu' alla sua unica domanda.

La cura non e' spegnere quelle righe — sparire in silenzio e' lo stesso difetto
girato dall'altra parte — e' mandarle in `livedub-banco-<data>.log`, dove restano
leggibili e non si confondono. Chi costruisce la finestra fuori dal vivo dichiara
`registro.banco()` **prima**, e una verifica lo ricava dal sorgente invece di
tenerne un elenco.
"""

from __future__ import annotations

import datetime as _dt
import sys
import threading
import traceback
from pathlib import Path

from core.preferenze import cartella
from core.versione import scheda

_APERTO = None
GIORNI = 7

# Le due famiglie di file. Sono separate anche nel nome perche' il primo che le
# guarda deve poterle distinguere **senza aprirle**, e perche' cosi' la pulizia
# dei sette giorni conta ogni famiglia per conto suo: un pomeriggio di schermate
# non deve poter buttare via il registro di ieri.
PREFISSO = "livedub"
PREFISSO_BANCO = "livedub-banco"

_BANCO = False


def nome(giorno, di_banco: bool) -> str:
    """Come si chiama il file del registro di quel giorno.

    **E' la regola, e sta qui apposta**: si prova senza aprire una finestra e
    senza toccare il disco, come `colore_stato` e `gravita` in `core/motore.py`.
    """
    radice = PREFISSO_BANCO if di_banco else PREFISSO
    return f"{radice}-{giorno.isoformat()}.log"


def cartella_log() -> Path:
    """La cartella dei registri. Pubblica perche' la guardano anche le prove."""
    c = cartella() / "log"
    c.mkdir(parents=True, exist_ok=True)
    return c


def _cartella() -> Path:
    return cartella_log()


def file_oggi(di_banco: bool | None = None) -> Path:
    """Il file su cui si scrive adesso (o su cui si scriverebbe)."""
    quale = _BANCO if di_banco is None else bool(di_banco)
    return _cartella() / nome(_dt.date.today(), quale)


def di_banco() -> bool:
    """Questo processo sta simulando?"""
    return _BANCO


def banco(attivo: bool = True) -> None:
    """«Quello che scrivo da qui non e' successo a nessuno.»

    La chiama chi costruisce la finestra **fuori dal vivo** — le schermate, i
    cataloghi, i due gruppi della suite che aprono una `Finestra` — prima di
    costruirla. Da quel momento il registro e' `livedub-banco-<data>.log`.

    Si puo' chiamare anche a registro gia' aperto: in quel caso si chiude e si
    riapre sull'altro file, se no basterebbe un import per fissare la scelta
    prima che chi di dovere abbia potuto dichiararla.
    """
    global _BANCO
    if bool(attivo) == _BANCO:
        return
    _BANCO = bool(attivo)
    if _APERTO is not None:
        chiudi()
        apri()


def chiudi() -> None:
    """Chiude il file, se e' aperto. Serve a `banco()` per cambiare famiglia."""
    global _APERTO
    if _APERTO is None:
        return
    try:
        _APERTO.close()
    except Exception:
        pass
    _APERTO = None


def apri() -> None:
    """Apre il registro di oggi e ci scrive la scheda della versione."""
    global _APERTO
    if _APERTO is not None:
        return
    try:
        _APERTO = file_oggi().open("a", encoding="utf-8")
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
    un altro modo di riempire il disco di qualcun altro.

    **Una famiglia per volta.** Con un `livedub-*.log` solo, un pomeriggio di
    schermate avrebbe fatto scadere il registro vero: i due elenchi si ordinano
    insieme e i sette superstiti sarebbero stati tutti di banco. La forma della
    data nel glob tiene separate le due famiglie, perche' `banco-2026-08-19` non
    sta in `????-??-??`.
    """
    try:
        for radice in (PREFISSO, PREFISSO_BANCO):
            file = sorted(_cartella().glob(f"{radice}-????-??-??.log"))
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

    # **`sys.excepthook` non vede i thread, ed e' li' che vive questo
    # programma.** I due cicli — audio a 10 ms e video a 30 Hz — girano ognuno
    # nel suo thread, e un'eccezione li' finisce in `threading.excepthook`: senza
    # questa riga, il gestore «niente esce di scena in silenzio» copriva l'unico
    # posto dove non succede quasi mai niente. E' la stessa cosa della domanda
    # 39, vista dal lato del registro: il thread audio moriva senza lasciare
    # traccia, e l'unico modo di accorgersene era che il doppiaggio ammutolisse.
    precedente_thread = threading.excepthook

    def mio_thread(dati) -> None:
        testo = "".join(
            traceback.format_exception(dati.exc_type, dati.exc_value, dati.exc_traceback)
        )
        nome = getattr(dati.thread, "name", "?")
        scrivi(f"GUASTO NON GESTITO nel thread {nome}\n" + testo)
        if al_guasto is not None:
            try:
                al_guasto(dati.exc_type, dati.exc_value, testo)
            except Exception:
                pass
        precedente_thread(dati)

    threading.excepthook = mio_thread


def percorso() -> Path:
    return _cartella()
