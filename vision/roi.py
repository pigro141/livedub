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


# **Quanto puo' essere alta l'area che si legge.** La regola stava in
# `vision/aree.py` insieme alle zone multiple; quelle sono state tolte, questa
# no — descrive un difetto della ROI, non delle zone.
ALTEZZA_MASSIMA = 0.30


def troppo_grande(roi) -> str:
    """Se l'area e' troppo alta per essere letta, dice perche'. Se no, `""`.

    Un'area grande non e' «meno precisa»: e' **muta**. Il cancello che decide se
    rileggere lo schermo guarda la *frazione* di pixel cambiati, e quella
    frazione ha l'area al denominatore: lo stesso sottotitolo diluito in un'area
    grande non la supera piu'. Misurato, a schermo intero: quattordici fotogrammi
    guardati, quattordici fermati, zero chiamate all'OCR — a telecamera ferma.

    E' una regola e sta fuori dalla finestra apposta: cosi' la si dice sia
    mentre si tira il rettangolo col mouse sia all'avvio della catena, e si
    verifica senza aprire niente.
    """
    h = float(roi[3])
    if h <= ALTEZZA_MASSIMA:
        return ""
    return (
        f"! l'area e' alta {h:.2f} dello schermo: sopra {ALTEZZA_MASSIMA:.2f} la "
        f"catena legge poco o niente. Il cancello che decide se rileggere guarda "
        f"la **frazione** di schermo cambiata, e lo stesso sottotitolo diluito in "
        f"un'area grande non la supera piu' (misurato: a schermo intero, zero "
        f"letture). Tira l'area stretta attorno alla riga."
    )
