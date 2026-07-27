"""Da letture per-frame a battute con un inizio e una fine.

Fra l'OCR e il resto della pipeline manca un pezzo di ragionamento. L'OCR
risponde alla domanda "cosa c'e' scritto adesso"; il doppiaggio ha bisogno di
sapere "quando e' comparsa una battuta nuova" e "quanto e' rimasta a schermo".
Sono domande diverse, e le insidie stanno tutte qui:

- un sottotitolo appare in **dissolvenza**, e la prima lettura cade su lettere
  mezze trasparenti: e' la lettura piu' probabile da sbagliare, e sarebbe anche
  quella che va in onda. Per questo una battuta si conferma solo dopo
  `stable_reads` letture concordi;
- confermare costa tempo, ma la battuta e' **comparsa prima**. Il `t_on` che
  finisce nell'evento e' quello della *prima* lettura, non della conferma: cosi'
  il conto della latenza resta onesto invece di regalarsi un frame;
- l'OCR sbaglia un carattere ogni tanto senza che il sottotitolo sia cambiato.
  Il confronto e' quindi per **somiglianza**, non per uguaglianza, altrimenti
  ogni sfarfallio verrebbe letto come una battuta nuova e il doppiatore
  ricomincerebbe la frase da capo;
- una riga puo' sparire per un solo frame e tornare. `hold_frames` evita di
  chiudere una battuta ancora in corso.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from core.config import VisionConfig
from core.types import LineClass, SubtitleEvent

_SPACES = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Forma di confronto: minuscole, spazi normalizzati.

    Serve solo a decidere se due letture sono *la stessa battuta*. Il testo che
    va in sintesi resta quello originale.
    """
    return _SPACES.sub(" ", text.strip().lower())


def similarity(a: str, b: str) -> float:
    """Somiglianza fra due letture, 0..1."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


@dataclass(slots=True)
class _Pending:
    """Candidata in attesa di conferma."""

    norm: str
    text: str
    count: int
    first_t: float
    cls: LineClass
    lines: tuple = ()


@dataclass(slots=True)
class TrackerOutput:
    """Cosa e' cambiato in questa passata."""

    opened: list[SubtitleEvent] = field(default_factory=list)
    closed: list[SubtitleEvent] = field(default_factory=list)

    @property
    def any(self) -> bool:
        return bool(self.opened or self.closed)


class SubtitleTracker:
    """Tiene lo stato dei sottotitoli a schermo.

    Funziona sia se alimentato a ogni frame sia se alimentato solo quando il
    rilevatore di cambiamento sveglia l'OCR: il conteggio delle assenze e'
    sulle *passate*, non sui frame.
    """

    def __init__(self, cfg: VisionConfig, min_similarity: float = 0.88) -> None:
        self.cfg = cfg
        self.min_similarity = min_similarity
        self._active: dict[str, SubtitleEvent] = {}
        self._pending: dict[str, _Pending] = {}
        self._missing: dict[str, int] = {}

    # -- stato -------------------------------------------------------------

    @property
    def active(self) -> list[SubtitleEvent]:
        return list(self._active.values())

    def reset(self) -> None:
        self._active.clear()
        self._pending.clear()
        self._missing.clear()

    # -- alimentazione -----------------------------------------------------

    def feed(
        self, candidates: list[SubtitleEvent], t: float, certain: bool = False
    ) -> TrackerOutput:
        """Passa le battute lette in questo istante. Restituisce cosa e' nato e
        cosa e' morto.

        `certain=True` significa "so per certo che quello che manca non c'e'
        piu'": chi chiama ha una prova indipendente dall'OCR, tipicamente il
        rilevatore di cambiamento che ha visto sparire l'inchiostro. In quel
        caso l'assenza si applica subito.

        La distinzione non e' pedanteria. `hold_frames` conta le *passate*, e le
        passate avvengono solo quando qualcosa cambia a schermo: senza questa
        scorciatoia una battuta sparita resterebbe aperta fino al successivo
        cambiamento qualunque, e la sua durata — che e' il dato su cui poggia
        tutta la calibrazione del tempo — risulterebbe piu' lunga del vero.
        """
        out = TrackerOutput()
        seen: dict[str, SubtitleEvent] = {}
        per_class: dict[LineClass, int] = {}
        for cand in candidates:
            n = per_class.get(cand.cls, 0)
            per_class[cand.cls] = n + 1
            seen[f"{cand.cls.value}#{n}"] = cand

        self._expire(seen, t, out, force=certain)

        for key, cand in seen.items():
            self._missing[key] = 0
            norm = normalize(cand.text)
            if not norm:
                continue

            current = self._active.get(key)
            if current is not None and similarity(normalize(current.text), norm) >= self.min_similarity:
                # Stessa battuta ancora a schermo: niente da fare. E' il caso
                # piu' frequente in assoluto.
                self._pending.pop(key, None)
                continue

            pending = self._pending.get(key)
            if pending is not None and similarity(pending.norm, norm) >= self.min_similarity:
                pending.count += 1
                # Fra due letture concordi si tiene la piu' ricca: la dissolvenza
                # toglie caratteri, non ne aggiunge.
                if len(cand.text) > len(pending.text):
                    pending.text = cand.text
                    pending.lines = cand.lines
            else:
                pending = _Pending(
                    norm=norm,
                    text=cand.text,
                    count=1,
                    first_t=cand.t_on,
                    cls=cand.cls,
                    lines=cand.lines,
                )
                self._pending[key] = pending

            if pending.count >= max(1, self.cfg.stable_reads):
                if current is not None:
                    out.closed.append(current.closed(t))
                event = SubtitleEvent(
                    text=pending.text,
                    cls=pending.cls,
                    t_on=pending.first_t,
                    lines=pending.lines,
                )
                self._active[key] = event
                out.opened.append(event)
                self._pending.pop(key, None)

        return out

    def close_all(self, t: float) -> list[SubtitleEvent]:
        """Chiude tutto. Da chiamare a fine sessione o a fine replay, altrimenti
        l'ultima battuta resterebbe senza durata."""
        closed = [ev.closed(t) for ev in self._active.values()]
        self._active.clear()
        self._pending.clear()
        self._missing.clear()
        return closed

    # -- interni -----------------------------------------------------------

    def _expire(
        self, seen: dict[str, SubtitleEvent], t: float, out: TrackerOutput, force: bool = False
    ) -> None:
        """Chiude le battute che non si vedono piu' da abbastanza passate."""
        hold = max(0, self.cfg.hold_frames)
        for key in list(self._active):
            if key in seen:
                continue
            missing = self._missing.get(key, 0) + 1
            self._missing[key] = missing
            if force or missing > hold:
                out.closed.append(self._active.pop(key).closed(t))
                self._missing.pop(key, None)
        for key in list(self._pending):
            if key in seen:
                continue
            # Una candidata mai confermata che sparisce era uno sfarfallio.
            missing = self._missing.get(key, 0) + 1
            self._missing[key] = missing
            if force or missing > hold:
                self._pending.pop(key, None)
                self._missing.pop(key, None)
