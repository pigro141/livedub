"""Ritaglio della regione dei sottotitoli.

La ROI e' in coordinate normalizzate perche' deve sopravvivere a un cambio di
risoluzione: lo stesso profilo di gioco vale a 1080p e a 1440p. La conversione
in pixel avviene qui, in un posto solo.
"""

from __future__ import annotations

import numpy as np


def roi_pixels(
    shape: tuple[int, ...], roi: tuple[float, float, float, float]
) -> tuple[int, int, int, int]:
    """Converte (x, y, w, h) normalizzati in (x, y, w, h) in pixel.

    Il rettangolo viene sempre riportato dentro il frame: una ROI che sborda per
    un arrotondamento deve produrre un ritaglio piu' piccolo, non un errore in
    mezzo a una partita.
    """
    h, w = int(shape[0]), int(shape[1])
    rx, ry, rw, rh = roi
    if rw <= 0 or rh <= 0:
        raise ValueError(f"ROI di area nulla: {roi}")
    x0 = max(0, min(w - 1, int(round(rx * w))))
    y0 = max(0, min(h - 1, int(round(ry * h))))
    x1 = max(x0 + 1, min(w, int(round((rx + rw) * w))))
    y1 = max(y0 + 1, min(h, int(round((ry + rh) * h))))
    return x0, y0, x1 - x0, y1 - y0


def crop(frame: np.ndarray, roi: tuple[float, float, float, float]) -> np.ndarray:
    """Vista (non copia) della ROI dentro il frame."""
    x, y, w, h = roi_pixels(frame.shape, roi)
    return frame[y : y + h, x : x + w]
