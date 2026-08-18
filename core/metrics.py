"""Registro delle misure.

Il progetto nasce con il vincolo di essere misurabile prima di essere veloce:
ogni stadio si cronometra da solo e deposita qui i suoi numeri. La regola e' che
nessuna affermazione sulle prestazioni vale se non esce da questo registro.

Sono deliberatamente esclusi la media come unica statistica e i tempi totali:
per una pipeline live conta la coda della distribuzione (p95/p99), perche' e' li'
che una battuta arriva tardi.
"""

from __future__ import annotations

import math
import threading
from collections import deque
from typing import Iterable


class Timer:
    """Serie di durate in millisecondi, con finestra scorrevole."""

    __slots__ = ("name", "_samples", "_count", "_sum", "_max", "_lock")

    def __init__(self, name: str, window: int = 512) -> None:
        self.name = name
        self._samples: deque[float] = deque(maxlen=window)
        self._count = 0
        self._sum = 0.0
        self._max = 0.0
        self._lock = threading.Lock()

    def add(self, ms: float) -> None:
        with self._lock:
            self._samples.append(ms)
            self._count += 1
            self._sum += ms
            if ms > self._max:
                self._max = ms

    @property
    def count(self) -> int:
        return self._count

    @property
    def mean(self) -> float:
        """Media su tutta la storia, non solo sulla finestra."""
        return self._sum / self._count if self._count else 0.0

    @property
    def max(self) -> float:
        return self._max

    @property
    def ultimo(self) -> float:
        """L'ultimo campione, o 0 se non ce n'e' nessuno.

        Serve a chi guarda **adesso** invece che a chi rilegge dopo: la finestra
        mostra la fretta chiesta all'ultima battuta, e un p50 li' risponderebbe a
        un'altra domanda — «com'e' andata la sessione» invece di «cos'e'
        appena successo».
        """
        with self._lock:
            return self._samples[-1] if self._samples else 0.0

    def percentile(self, q: float) -> float:
        """Percentile sulla finestra corrente. `q` in [0, 1]."""
        if not 0.0 <= q <= 1.0:
            raise ValueError(f"percentile fuori range: {q}")
        with self._lock:
            data = sorted(self._samples)
        if not data:
            return 0.0
        if len(data) == 1:
            return data[0]
        # Interpolazione lineare fra i due campioni adiacenti.
        pos = q * (len(data) - 1)
        low = math.floor(pos)
        high = math.ceil(pos)
        if low == high:
            return data[low]
        return data[low] + (data[high] - data[low]) * (pos - low)

    @property
    def p50(self) -> float:
        return self.percentile(0.50)

    @property
    def p95(self) -> float:
        return self.percentile(0.95)

    @property
    def p99(self) -> float:
        return self.percentile(0.99)

    def snapshot(self) -> dict:
        return {
            "count": self.count,
            "mean_ms": round(self.mean, 3),
            "p50_ms": round(self.p50, 3),
            "p95_ms": round(self.p95, 3),
            "p99_ms": round(self.p99, 3),
            "max_ms": round(self.max, 3),
        }

    def reset(self) -> None:
        with self._lock:
            self._samples.clear()
            self._count = 0
            self._sum = 0.0
            self._max = 0.0


class Counter:
    """Contatore monotono. Serve per gli eventi: battute dette, righe scartate,
    sforamenti di scadenza."""

    __slots__ = ("name", "_value", "_lock")

    def __init__(self, name: str) -> None:
        self.name = name
        self._value = 0
        self._lock = threading.Lock()

    def inc(self, by: int = 1) -> int:
        with self._lock:
            self._value += by
            return self._value

    @property
    def value(self) -> int:
        return self._value

    def reset(self) -> None:
        with self._lock:
            self._value = 0


class MetricsRegistry:
    """Contenitore unico di timer e contatori, indicizzati per nome."""

    def __init__(self) -> None:
        self._timers: dict[str, Timer] = {}
        self._counters: dict[str, Counter] = {}
        self._lock = threading.Lock()

    def timer(self, name: str) -> Timer:
        with self._lock:
            t = self._timers.get(name)
            if t is None:
                t = Timer(name)
                self._timers[name] = t
            return t

    def counter(self, name: str) -> Counter:
        with self._lock:
            c = self._counters.get(name)
            if c is None:
                c = Counter(name)
                self._counters[name] = c
            return c

    @property
    def timer_names(self) -> list[str]:
        return sorted(self._timers)

    @property
    def counter_names(self) -> list[str]:
        return sorted(self._counters)

    def snapshot(self) -> dict:
        return {
            "timers": {n: self._timers[n].snapshot() for n in self.timer_names},
            "counters": {n: self._counters[n].value for n in self.counter_names},
        }

    def reset(self) -> None:
        for t in self._timers.values():
            t.reset()
        for c in self._counters.values():
            c.reset()

    def report(self, only: Iterable[str] | None = None) -> str:
        """Tabella leggibile a terminale. `only` filtra per prefisso di nome."""
        prefixes = tuple(only) if only else None

        def keep(name: str) -> bool:
            return prefixes is None or name.startswith(prefixes)

        lines: list[str] = []
        names = [n for n in self.timer_names if keep(n)]
        if names:
            width = max(len(n) for n in names)
            lines.append(f"{'stadio'.ljust(width)}    n     p50      p95      p99      max")
            lines.append("-" * (width + 42))
            for n in names:
                t = self._timers[n]
                lines.append(
                    f"{n.ljust(width)} {t.count:>5} "
                    f"{t.p50:>7.2f}  {t.p95:>7.2f}  {t.p99:>7.2f}  {t.max:>7.2f}"
                )
        cnames = [n for n in self.counter_names if keep(n)]
        if cnames:
            if lines:
                lines.append("")
            width = max(len(n) for n in cnames)
            for n in cnames:
                lines.append(f"{n.ljust(width)}  {self._counters[n].value}")
        return "\n".join(lines) if lines else "(nessuna misura raccolta)"
