"""Rilevatore di cambiamento sulla ROI.

E' il cancello che sta davanti all'OCR. L'OCR e' la cosa cara del dominio video
e un sottotitolo resta a schermo per decine di frame: farlo girare a ogni frame
significherebbe rileggere cinquanta volte la stessa battuta.

Il diff invece deve costare quasi nulla, perche' gira a 30 Hz sempre. Due
scelte per ottenerlo: si lavora sulla sola luminanza, e la si sottocampiona di
`stride` in entrambe le direzioni — con stride 4 si guarda un pixel su sedici.
Un sottotitolo che compare cambia una frazione enorme della ROI, quindi la
perdita di risoluzione non costa sensibilita' dove serve.

Il rilevatore non dice solo "cambiato": distingue **comparsa**, **sparizione** e
**sostituzione**, che a valle sono tre cose diverse — la sparizione chiude una
battuta e ne fissa la durata reale, la sostituzione ne chiude una e ne apre
un'altra nello stesso istante.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np


class Change(Enum):
    NONE = "none"
    APPEARED = "appeared"
    VANISHED = "vanished"
    REPLACED = "replaced"


@dataclass(slots=True)
class DiffResult:
    change: Change
    ratio: float  # frazione di pixel campionati che sono cambiati
    ink: float  # frazione di pixel campionati che sono testo, adesso

    @property
    def changed(self) -> bool:
        return self.change is not Change.NONE


class RoiDiff:
    """Confronta la ROI corrente con la precedente."""

    def __init__(self, threshold: float = 0.004, stride: int = 4, ink_min_luma: int = 110) -> None:
        if stride < 1:
            raise ValueError(f"stride non valido: {stride}")
        self.threshold = float(threshold)
        self.stride = int(stride)
        self.ink_min_luma = int(ink_min_luma)
        self._previous: np.ndarray | None = None
        self._had_ink = False

    def reset(self) -> None:
        self._previous = None
        self._had_ink = False

    def update(self, roi: np.ndarray) -> DiffResult:
        sample = self._sample(roi)
        ink_mask = sample > self.ink_min_luma
        ink = float(ink_mask.mean()) if ink_mask.size else 0.0
        has_ink = ink > 0.0

        if self._previous is None:
            self._previous = sample
            self._had_ink = has_ink
            # Il primo frame non e' un cambiamento: e' l'inizio delle
            # osservazioni. Se pero' c'e' gia' del testo, e' una comparsa —
            # altrimenti un sottotitolo gia' a schermo all'avvio non verrebbe
            # mai letto.
            return DiffResult(Change.APPEARED if has_ink else Change.NONE, 0.0, ink)

        if sample.shape != self._previous.shape:
            # Cambio di risoluzione a meta' sessione: si riparte da zero.
            self._previous = sample
            self._had_ink = has_ink
            return DiffResult(Change.APPEARED if has_ink else Change.NONE, 1.0, ink)

        delta = np.abs(sample - self._previous)
        ratio = float((delta > 16.0).mean())
        had_ink = self._had_ink
        self._previous = sample
        self._had_ink = has_ink

        if ratio <= self.threshold:
            return DiffResult(Change.NONE, ratio, ink)
        if has_ink and not had_ink:
            change = Change.APPEARED
        elif had_ink and not has_ink:
            change = Change.VANISHED
        elif has_ink:
            change = Change.REPLACED
        else:
            # Cambia qualcosa ma non c'e' testo ne' prima ne' dopo: e' lo sfondo
            # del gioco che si muove sotto la ROI. Non riguarda i sottotitoli.
            change = Change.NONE
        return DiffResult(change, ratio, ink)

    def _sample(self, roi: np.ndarray) -> np.ndarray:
        if roi.ndim == 3:
            small = roi[:: self.stride, :: self.stride, :3]
            return small.astype(np.float32).mean(axis=2)
        return roi[:: self.stride, :: self.stride].astype(np.float32)
