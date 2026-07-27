"""Lo stadio: unita' base della pipeline.

Uno stadio fa una cosa sola, si cronometra da solo e si puo' spegnere. Questi
tre requisiti insieme sono il motivo per cui esiste una classe invece di
funzioni sciolte:

- **cronometrarsi da solo** perche' una misura che va aggiunta a mano viene
  aggiunta solo dove si sospetta gia' il problema, cioe' mai dove serve;
- **spegnersi** perche' il modo piu' rapido di scoprire chi costa e' togliergli
  la corrente e rimisurare, e perche' i test devono poter forzare i backend
  leggeri senza scaricare modelli;
- **non far cadere la pipeline** quando fallisce: in gioco uno stadio che va in
  errore deve degradare, non spegnere il doppiaggio a meta' scena.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Iterable

from core.clock import Clock, get_clock
from core.metrics import MetricsRegistry


class Stage:
    """Base di ogni stadio. Le sottoclassi implementano `process`.

    `on_error`:
      - `"raise"`  propaga l'eccezione. Default: sul banco un errore deve gridare.
      - `"bypass"` conta l'errore e restituisce il risultato di `bypass()`.
        E' la modalita' del live, dove perdere una battuta e' meglio che
        perdere la sessione.

    **Due tempi, non uno.** Uno stadio ha bisogno di sapere che ora e' nel
    *media* (per timbrare gli eventi: quel sottotitolo compare al secondo 41,3
    del video) e quanto e' *costato* girare (per sapere se sta in budget). Sono
    grandezze diverse e vanno da orologi diversi:

    - `self.clock` e' il tempo del media, virtualizzabile. Nel replay avanza a
      comando, molto piu' in fretta del reale.
    - il costo si misura **sempre** a muro, con `perf_counter`.

    Confonderli e' allettante e sbagliato: misurando il costo sull'orologio
    virtuale, in replay ogni stadio risulta gratis — la misura non e' imprecisa,
    e' proprio incapace di esprimere la risposta. `cost_now` resta iniettabile
    perche' i test devono poter verificare il cronometro senza dormire davvero.
    """

    def __init__(
        self,
        name: str,
        *,
        metrics: MetricsRegistry | None = None,
        clock: Clock | None = None,
        enabled: bool = True,
        on_error: str = "raise",
        cost_now: Callable[[], float] | None = None,
    ) -> None:
        if on_error not in ("raise", "bypass"):
            raise ValueError(f"on_error sconosciuto: {on_error!r}")
        self.name = name
        self.enabled = enabled
        self.on_error = on_error
        self.metrics = metrics if metrics is not None else MetricsRegistry()
        self._clock = clock
        self._cost_now = cost_now if cost_now is not None else time.perf_counter
        self._timer = self.metrics.timer(name)
        self._calls = self.metrics.counter(f"{name}.calls")
        self._errors = self.metrics.counter(f"{name}.errors")
        self._skips = self.metrics.counter(f"{name}.skipped")

    @property
    def clock(self) -> Clock:
        # Risolto a ogni accesso: il replay puo' sostituire l'orologio globale
        # dopo che gli stadi sono gia' stati costruiti.
        return self._clock if self._clock is not None else get_clock()

    # -- da implementare nelle sottoclassi ---------------------------------

    def process(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError(f"{type(self).__name__}.process non implementato")

    def bypass(self, *args: Any, **kwargs: Any) -> Any:
        """Cosa produce lo stadio quando e' spento o e' fallito in modalita'
        `bypass`. Il default lascia passare il primo argomento: va bene per gli
        stadi che trasformano, va sovrascritto da quelli che producono."""
        return args[0] if args else None

    # -- ingresso pubblico -------------------------------------------------

    def run(self, *args: Any, **kwargs: Any) -> Any:
        if not self.enabled:
            self._skips.inc()
            return self.bypass(*args, **kwargs)
        t0 = self._cost_now()
        try:
            result = self.process(*args, **kwargs)
        except Exception:
            self._errors.inc()
            self._timer.add((self._cost_now() - t0) * 1000.0)
            if self.on_error == "raise":
                raise
            return self.bypass(*args, **kwargs)
        self._timer.add((self._cost_now() - t0) * 1000.0)
        self._calls.inc()
        return result

    __call__ = run

    # -- introspezione -----------------------------------------------------

    @property
    def elapsed(self):
        return self._timer

    @property
    def errors(self) -> int:
        return self._errors.value

    def __repr__(self) -> str:
        state = "on" if self.enabled else "off"
        return f"<{type(self).__name__} {self.name} [{state}] n={self._timer.count}>"


class FnStage(Stage):
    """Stadio costruito attorno a una funzione. Utile per i pezzi banali e per
    i finti backend del banco di prova."""

    def __init__(self, name: str, fn: Callable[..., Any], **kw: Any) -> None:
        super().__init__(name, **kw)
        self._fn = fn

    def process(self, *args: Any, **kwargs: Any) -> Any:
        return self._fn(*args, **kwargs)


class Chain(Stage):
    """Sequenza di stadi: l'uscita di uno entra nel successivo.

    Si cronometra come un tutto, oltre ai cronometri dei singoli stadi, cosi' la
    somma delle parti si puo' confrontare con il totale — la differenza e' il
    costo dell'impalcatura, ed e' bene vederlo.
    """

    def __init__(self, name: str, stages: Iterable[Stage], **kw: Any) -> None:
        super().__init__(name, **kw)
        self.stages: list[Stage] = list(stages)

    def process(self, value: Any = None) -> Any:
        for stage in self.stages:
            value = stage.run(value)
        return value

    def find(self, name: str) -> Stage | None:
        for stage in self.stages:
            if stage.name == name:
                return stage
            if isinstance(stage, Chain):
                found = stage.find(name)
                if found is not None:
                    return found
        return None

    def set_enabled(self, name: str, enabled: bool) -> bool:
        """Accende o spegne uno stadio per nome. Restituisce False se non c'e'."""
        stage = self.find(name)
        if stage is None:
            return False
        stage.enabled = enabled
        return True

    def __len__(self) -> int:
        return len(self.stages)

    def __iter__(self):
        return iter(self.stages)
