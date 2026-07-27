"""Orologio della pipeline.

Ogni timestamp del progetto passa da qui e mai da `time.perf_counter()` diretto.
Il motivo e' il banco di prova: durante il replay da file il tempo deve poter
avanzare a comando, molto piu' veloce del reale, in modo che due esecuzioni
sullo stesso video producano esattamente gli stessi eventi. Se anche un solo
stadio leggesse l'orologio di sistema, il replay smetterebbe di essere
deterministico e i confronti prima/dopo una modifica non varrebbero piu' nulla.
"""

from __future__ import annotations

import threading
import time
from typing import Protocol


class Clock(Protocol):
    """Sorgente di tempo monotona, in secondi."""

    def now(self) -> float:
        ...


class RealClock:
    """Tempo reale. Usato in gioco."""

    __slots__ = ("_origin",)

    def __init__(self) -> None:
        self._origin = time.perf_counter()

    def now(self) -> float:
        return time.perf_counter() - self._origin

    def __repr__(self) -> str:
        return f"RealClock(t={self.now():.3f})"


class VirtualClock:
    """Tempo pilotato a mano. Usato dal replay.

    Non scorre da solo: avanza solo quando il replay lo fa avanzare, cosi' la
    pipeline puo' macinare un'ora di video in un minuto restando coerente sui
    timestamp.
    """

    __slots__ = ("_t", "_lock")

    def __init__(self, start: float = 0.0) -> None:
        self._t = float(start)
        self._lock = threading.Lock()

    def now(self) -> float:
        return self._t

    def advance(self, dt: float) -> float:
        """Avanza di `dt` secondi (deve essere >= 0) e restituisce il nuovo tempo."""
        if dt < 0:
            raise ValueError(f"il tempo non torna indietro: dt={dt}")
        with self._lock:
            self._t += dt
            return self._t

    def set(self, t: float) -> float:
        """Porta l'orologio a `t`. Vietato indietreggiare: nasconderebbe i bug."""
        with self._lock:
            if t < self._t:
                raise ValueError(f"il tempo non torna indietro: {t} < {self._t}")
            self._t = float(t)
            return self._t

    def __repr__(self) -> str:
        return f"VirtualClock(t={self._t:.3f})"


# Orologio di default del processo. Gli stadi che non ne ricevono uno esplicito
# usano questo: comodo, ma il replay lo sostituisce all'avvio con un VirtualClock.
_default: Clock = RealClock()


def get_clock() -> Clock:
    return _default


def set_clock(clock: Clock) -> Clock:
    """Sostituisce l'orologio di default e restituisce il precedente."""
    global _default
    previous = _default
    _default = clock
    return previous
