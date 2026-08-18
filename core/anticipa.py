"""Preparare il testo di una battuta **mentre** si aspetta di sapere chi parla.

## Perche' esiste

La catena aveva due attese in fila che non hanno niente da dirsi:

    sottotitolo confermato -> [ 500 ms per sapere CHI parla ] -> [ traduci ] -> voce

I 500 ms (`speaker.decide_after_ms`) servono ad avere mezzo secondo del parlato
di questo personaggio da dare all'impronta: e' una domanda sull'**audio**. La
traduzione ha bisogno del **testo**, che esiste gia' quando il sottotitolo viene
confermato. Sono due domande indipendenti, e metterle in coda costa la somma
invece del massimo.

Misurato sulle sessioni dal vivo archiviate (`runs/`), per battuta:

    attesa (kokoro, traduzione spenta)   538-553 ms   p50, molto stabile
    residuo con google                    +97 -> +490 ms   (dipende dalla rete)
    residuo con ollama/TranslateGemma     +780 -> +810 ms

cioe' fra un sesto e nove decimi della latenza totale sono un'attesa che poteva
avvenire dentro un'altra attesa.

## Cosa fa questo modulo, e cosa **non** fa

E' un anticipo generico: `chiedi(testo)` mette il testo in coda a un lavoratore,
`prendi(testo)` restituisce il risultato — subito se e' pronto, aspettandolo se
e' in volo, calcolandolo sul posto se nessuno l'aveva chiesto. Non sa cosa sia
una traduzione: la funzione gliela passa chi lo costruisce.

**Un lavoratore solo**, e non e' prudenza: due traduzioni insieme si contendono
la stessa rete o la stessa GPU e le perdono tutte e due — la stessa aritmetica
gia' scritta per `_turno_sintesi` in `core/pipeline.py`. E in coda ci vanno nello
stesso ordine in cui verranno dette, quindi la prima a servire e' la prima a
partire.

## Le tre decisioni che contano

**Se non e' pronta, si aspetta: non si parte con l'originale.** «Non ancora
pronta» non e' «fallita». La politica del progetto — se la traduzione fallisce si
tiene l'originale — vale per un fallimento, dove l'alternativa e' una battuta
muta; qui l'alternativa e' la stessa battuta mezzo secondo dopo. Partire con
l'originale vorrebbe dire consegnare una battuta nella lingua sbagliata **a
caso**, cioe' la stessa scena doppiata meta' in una lingua e meta' nell'altra a
seconda di com'e' andata la rete in quel secondo. Aspettare non e' mai peggio di
oggi: oggi si aspetta comunque, solo dopo invece che durante.

**Il ricordo ha un tetto.** Cresce di una voce per battuta e in questo progetto
tre cose sono gia' cresciute senza fermarsi (`spoken`, `closed`, la cache delle
voci). Le ultime `memoria` bastano: chi chiede e' sempre la battuta di adesso.

**Fermarsi non lascia nessuno appeso.** `ferma()` sveglia chi sta aspettando con
il testo di partenza invece di lasciarlo su una `Event` che nessuno mettera' piu':
una suite appesa non e' rossa, e' muta — dieci minuti senza stampare una riga,
gia' successo qui con il dialogo modale della guida.
"""

from __future__ import annotations

import queue
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True, slots=True)
class Preparato:
    """Il testo di una battuta nei tre stadi in cui serve a valle.

    Sono tre e non uno perche' a valle servono tutti e tre: `grezzo` e' la chiave
    con cui il cancello anti-doppioni confronta le riletture, `corretto` e' cio'
    che finisce in `SpokenLine.text_original` (la colonna «cosa c'era scritto»
    della prova d'ascolto), `finale` e' cio' che si pronuncia.
    """

    grezzo: str  # come l'ha letto l'OCR, tolta l'etichetta del personaggio
    corretto: str  # dopo il Revisore
    finale: str  # dopo la traduzione
    ms: float = 0.0  # quanto e' costato prepararlo, **a muro**


class Anticipo:
    """Fa fare a un lavoratore cio' che servira' fra mezzo secondo."""

    def __init__(
        self,
        prepara: Callable[[str], Preparato],
        *,
        memoria: int = 256,
        metrics=None,
        nome: str = "translate",
        attesa_max_s: float = 30.0,
    ) -> None:
        self._prepara = prepara
        self._memoria = max(1, int(memoria))
        self._attesa_max_s = float(attesa_max_s)
        self._fatti: "OrderedDict[str, Preparato]" = OrderedDict()
        self._in_volo: dict[str, threading.Event] = {}
        self._lock = threading.Lock()
        self._coda: "queue.Queue[str | None]" = queue.Queue()
        self._thread: threading.Thread | None = None
        self._chiuso = False
        # I tre esiti, contati. Servono a leggere `translate.attesa`: un p50 a
        # zero puo' voler dire «l'anticipo funziona» oppure «non e' mai stato
        # chiesto», e sono due cose opposte.
        if metrics is not None:
            self._n_anticipate = metrics.counter(f"{nome}.anticipate")
            self._n_attese = metrics.counter(f"{nome}.attese")
            self._n_inline = metrics.counter(f"{nome}.inline")
        else:  # pragma: no cover - solo per usi fuori dalla pipeline
            from core.metrics import Counter

            self._n_anticipate = Counter(f"{nome}.anticipate")
            self._n_attese = Counter(f"{nome}.attese")
            self._n_inline = Counter(f"{nome}.inline")

    # -- ingresso ----------------------------------------------------------

    def chiedi(self, testo: str) -> bool:
        """Prepara questo testo, se non e' gia' fatto o in corso.

        Torna `True` se ha davvero messo qualcosa in coda. Si puo' chiamare a
        ogni fotogramma sullo stesso testo: costa una ricerca in un dizionario.
        """
        if self._chiuso or not testo:
            return False
        with self._lock:
            if testo in self._fatti or testo in self._in_volo:
                return False
            self._in_volo[testo] = threading.Event()
        self._avvia()
        self._coda.put(testo)
        return True

    def prendi(self, testo: str) -> Preparato:
        """Il testo preparato. Aspetta se e' in volo, lo fa qui se non lo e'."""
        if not testo:
            return Preparato(testo, testo, testo, 0.0)
        atteso = False
        while True:
            qui = False
            with self._lock:
                pronto = self._fatti.get(testo)
                if pronto is not None:
                    self._fatti.move_to_end(testo)
                    (self._n_attese if atteso else self._n_anticipate).inc()
                    return pronto
                evento = self._in_volo.get(testo)
                if evento is None:
                    # Nessuno l'aveva chiesta: si fa qui, che e' il comportamento
                    # di sempre. Si segna in volo prima di lasciare il lucchetto,
                    # cosi' il lavoratore non la rifa' se intanto qualcuno la
                    # chiede.
                    self._in_volo[testo] = threading.Event()
                    qui = True
            if qui:
                # **Fuori dal lucchetto**: `_lavora` lo riprende, e questo non e'
                # rientrante.
                self._n_inline.inc()
                return self._lavora(testo)
            atteso = True
            if not evento.wait(self._attesa_max_s):
                # Non e' mai successo e non deve poter appendere il doppiaggio:
                # si rifa' qui e si dichiara, perche' un'attesa infinita e' muta.
                print(
                    f"anticipo: {testo[:40]!r} non e' arrivato in "
                    f"{self._attesa_max_s:.0f}s: rifatto sul posto",
                    file=sys.stderr,
                )
                with self._lock:
                    self._in_volo.pop(testo, None)
                    self._in_volo[testo] = threading.Event()
                self._n_inline.inc()
                return self._lavora(testo)

    def ferma(self) -> None:
        """Chiude il lavoratore e non lascia nessuno ad aspettare."""
        if self._chiuso:
            return
        self._chiuso = True
        self._coda.put(None)
        t = self._thread
        if t is not None:
            t.join(timeout=2.0)
        with self._lock:
            appesi = list(self._in_volo.items())
            self._in_volo.clear()
        for testo, evento in appesi:
            # Chi aspettava riceve il testo di partenza: la sessione sta
            # finendo, e una battuta nella lingua sbagliata e' meglio di un
            # thread che non torna piu'.
            with self._lock:
                self._fatti.setdefault(testo, Preparato(testo, testo, testo, 0.0))
            evento.set()

    # -- dentro ------------------------------------------------------------

    def _avvia(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._ciclo, name="anticipo", daemon=True
            )
            self._thread.start()

    def _ciclo(self) -> None:
        while True:
            testo = self._coda.get()
            if testo is None:
                return
            with self._lock:
                # Gia' fatto da chi lo aspettava: non si rifa'. Ma l'attesa si
                # chiude comunque, se no chi e' fermo su quella `Event` non si
                # sveglia piu' — e un thread appeso non e' rosso, e' muto.
                gia = testo in self._fatti
                evento = self._in_volo.pop(testo, None) if gia else None
            if gia:
                if evento is not None:
                    evento.set()
                continue
            self._lavora(testo)

    def _lavora(self, testo: str) -> Preparato:
        t0 = time.perf_counter()
        try:
            p = self._prepara(testo)
        except Exception as e:  # pragma: no cover - dipende dal backend
            # **Si tiene l'originale**, che e' la politica gia' scritta: una
            # battuta nella lingua sbagliata e' un difetto, una battuta muta e'
            # un buco. Ma lo si dice: un ripiego silenzioso e' peggio di un
            # errore.
            print(f"anticipo: preparazione fallita: {e!r}", file=sys.stderr)
            p = Preparato(testo, testo, testo, (time.perf_counter() - t0) * 1000.0)
        with self._lock:
            self._fatti[testo] = p
            self._fatti.move_to_end(testo)
            while len(self._fatti) > self._memoria:
                self._fatti.popitem(last=False)
            evento = self._in_volo.pop(testo, None)
        if evento is not None:
            evento.set()
        return p

    # -- introspezione -----------------------------------------------------

    @property
    def in_volo(self) -> int:
        with self._lock:
            return len(self._in_volo)

    @property
    def pronti(self) -> int:
        with self._lock:
            return len(self._fatti)

    def __repr__(self) -> str:  # pragma: no cover - diagnostica
        return (
            f"<Anticipo pronti={self.pronti} in_volo={self.in_volo} "
            f"anticipate={self._n_anticipate.value} attese={self._n_attese.value} "
            f"inline={self._n_inline.value}>"
        )
