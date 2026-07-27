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
  chiudere una battuta ancora in corso;

- **una battuta non ha un posto fisso.** La prima versione teneva lo stato in un
  dizionario indicizzato per classe e posizione (`white#0`, `white#1`), il che
  sembra ovvio finche' a schermo c'e' solo il dialogo. Sulla registrazione vera
  una banda di texture — un cordolo, una striscia bianca — viene classificata
  bianca, si infila *sopra* la riga vera e le sposta l'indice: la stessa frase
  diventa `white#1` e il tracker la legge come una battuta nuova. Misurato: 55
  aperture in 50 secondi dove ne servivano una ventina. L'identita' di una
  battuta e' il suo **testo**, non la sua riga, quindi l'abbinamento e' per
  somiglianza fra tutte le attive della stessa classe.
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
    missing: int = 0


@dataclass(slots=True)
class _Tracked:
    """Battuta confermata e ancora a schermo."""

    event: SubtitleEvent
    missing: int = 0


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
        self._active: dict[int, _Tracked] = {}
        self._pending: dict[int, _Pending] = {}
        self._next_id = 0

    # -- stato -------------------------------------------------------------

    @property
    def active(self) -> list[SubtitleEvent]:
        return [tr.event for tr in self._active.values()]

    def reset(self) -> None:
        self._active.clear()
        self._pending.clear()
        self._next_id = 0

    def _new_id(self) -> int:
        self._next_id += 1
        return self._next_id

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
        matched_active: set[int] = set()
        matched_pending: set[int] = set()
        unmatched: list[tuple[SubtitleEvent, str]] = []

        # 1. Le candidate che continuano una battuta gia' a schermo. E' il caso
        #    di gran lunga piu' frequente: un sottotitolo resta per decine di
        #    frame e a ogni passata si ritrova identico a se stesso.
        for cand in candidates:
            norm = normalize(cand.text)
            if not norm:
                continue
            aid = self._best(self._active, cand.cls, norm, matched_active, lambda tr: normalize(tr.event.text))
            if aid is not None:
                matched_active.add(aid)
                self._active[aid].missing = 0
            else:
                unmatched.append((cand, norm))

        # 2. Le altre: o confermano una candidata in attesa, o ne aprono una.
        for cand, norm in unmatched:
            pid = self._best(self._pending, cand.cls, norm, matched_pending, lambda p: p.norm)
            if pid is None:
                pid = self._new_id()
                self._pending[pid] = _Pending(
                    norm=norm,
                    text=cand.text,
                    count=1,
                    first_t=cand.t_on,
                    cls=cand.cls,
                    lines=cand.lines,
                )
            else:
                pending = self._pending[pid]
                pending.count += 1
                pending.missing = 0
                # Fra due letture concordi si tiene la piu' ricca: la dissolvenza
                # toglie caratteri, non ne aggiunge.
                if len(cand.text) > len(pending.text):
                    pending.text = cand.text
                    pending.lines = cand.lines
            matched_pending.add(pid)

            pending = self._pending[pid]
            if pending.count < max(1, self.cfg.stable_reads):
                continue

            # Conferma. Se a schermo c'era **una sola** battuta della stessa
            # classe e non e' stata ritrovata, questa la sostituisce e quella si
            # chiude adesso: una battuta che lascia il posto alla successiva
            # senza passare per lo schermo vuoto finirebbe altrimenti a durare
            # `hold_frames` passate di troppo. Con piu' di una candidata a
            # sostituirla non si sa quale sia, e si lascia decidere alla scadenza.
            orphans = [
                a
                for a, tr in self._active.items()
                if a not in matched_active and tr.event.cls is pending.cls
            ]
            if len(orphans) == 1:
                old = self._active.pop(orphans[0])
                out.closed.append(old.event.closed(t))

            event = SubtitleEvent(
                text=pending.text, cls=pending.cls, t_on=pending.first_t, lines=pending.lines
            )
            self._active[pid] = _Tracked(event)
            matched_active.add(pid)
            out.opened.append(event)
            del self._pending[pid]

        self._expire(matched_active, matched_pending, t, out, force=certain)
        return out

    def _best(self, pool: dict, cls: LineClass, norm: str, taken: set, text_of) -> int | None:
        """L'elemento del gruppo piu' somigliante, sopra soglia. `None` se nessuno.

        Si sceglie il **migliore** e non il primo sopra soglia: con due battute
        della stessa classe a schermo — che e' il caso di una frase andata a capo
        letta come due righe — il primo sopra soglia puo' essere l'altra.
        """
        best_id, best_score = None, self.min_similarity
        for key, item in pool.items():
            if key in taken:
                continue
            item_cls = item.cls if isinstance(item, _Pending) else item.event.cls
            if item_cls is not cls:
                continue
            score = similarity(text_of(item), norm)
            if score >= best_score:
                best_id, best_score = key, score
        return best_id

    def close_all(self, t: float) -> list[SubtitleEvent]:
        """Chiude tutto. Da chiamare a fine sessione o a fine replay, altrimenti
        l'ultima battuta resterebbe senza durata."""
        closed = [tr.event.closed(t) for tr in self._active.values()]
        self._active.clear()
        self._pending.clear()
        return closed

    # -- interni -----------------------------------------------------------

    def _expire(
        self,
        matched_active: set[int],
        matched_pending: set[int],
        t: float,
        out: TrackerOutput,
        force: bool = False,
    ) -> None:
        """Chiude le battute che non si vedono piu' da abbastanza passate."""
        hold = max(0, self.cfg.hold_frames)
        for key in list(self._active):
            if key in matched_active:
                continue
            tracked = self._active[key]
            tracked.missing += 1
            if force or tracked.missing > hold:
                out.closed.append(self._active.pop(key).event.closed(t))
        for key in list(self._pending):
            if key in matched_pending:
                continue
            # Una candidata mai confermata che sparisce era uno sfarfallio.
            pending = self._pending[key]
            pending.missing += 1
            if force or pending.missing > hold:
                del self._pending[key]
