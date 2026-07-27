"""Dalla ROI alle righe di testo, classificate per colore.

E' il primo stadio del dominio video e la fondamenta di tutto il resto: se qui
una riga di suggerimento passa per dialogo, il doppiaggio legge ad alta voce
"premi E per entrare"; se una riga grigia viene fusa con quella bianca sopra,
due personaggi diventano uno.

**Nota sull'ordine dei canali.** Le due grandezze usate per classificare sono la
luminanza (media sui canali) e la saturazione (max meno min sui canali):
entrambe sono simmetriche rispetto all'ordine dei canali, quindi RGB e BGR danno
lo stesso risultato. Non e' un caso ma una scelta — la cattura Windows produce
BGRA e un'inversione di canali e' il tipo di bug che non da' errore, cambia solo
i risultati. Qui non puo' succedere.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from core.config import VisionConfig
from core.types import LineClass


@dataclass(slots=True)
class LineBand:
    """Una banda orizzontale di testo trovata nella ROI."""

    top: int
    bottom: int  # incluso
    cls: LineClass
    luma: float  # luminanza del corpo dei glifi
    sat: float  # saturazione massima sui pixel di testo
    # Ritaglio pronto per l'OCR: la luminanza vera dove c'e' testo, nero
    # altrove. NON binario, e la differenza si misura — il riconoscitore e'
    # addestrato su testo antialiasato, e una maschera a due livelli gli toglie
    # proprio le sfumature dei bordi su cui conta. Passando dal binario al
    # grigio mascherato il CER scende da 4,4% a 2,9% sul bianco e da 5,5% a
    # 4,0% sul grigio, a parita' di costo.
    crop: np.ndarray
    x0: int = 0
    x1: int = 0  # escluso

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.x0, self.top, self.x1 - self.x0, self.height)


def luma_sat(roi: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Luminanza e saturazione della ROI, come float32.

    Su un'immagine a 3 canali entrambe si calcolano senza sapere se e' RGB o
    BGR. Se arriva un canale alfa (BGRA della cattura Windows) viene scartato.
    """
    if roi.ndim == 2:
        luma = roi.astype(np.float32)
        return luma, np.zeros_like(luma)
    if roi.ndim != 3:
        raise ValueError(f"ROI con forma inattesa: {roi.shape}")
    rgb = roi[:, :, :3].astype(np.float32)
    luma = rgb.mean(axis=2)
    sat = rgb.max(axis=2) - rgb.min(axis=2)
    return luma, sat


def find_bands(text_mask: np.ndarray, min_height: int, min_pixels: int = 1) -> list[tuple[int, int]]:
    """Righe di testo come gruppi di righe-pixel contigue non vuote.

    `min_pixels` alza l'asticella su quanti pixel di testo servono perche' una
    riga-pixel conti: uno solo e' rumore di compressione, non una lettera.
    """
    profile = text_mask.sum(axis=1)
    active = profile >= min_pixels
    bands: list[tuple[int, int]] = []
    start: int | None = None
    for i, on in enumerate(active):
        if on and start is None:
            start = i
        elif not on and start is not None:
            if i - start >= min_height:
                bands.append((start, i - 1))
            start = None
    if start is not None and len(active) - start >= min_height:
        bands.append((start, len(active) - 1))
    return bands


def text_mask(luma: np.ndarray, cfg: VisionConfig) -> np.ndarray:
    """Quali pixel sono testo.

    La soglia assoluta da sola non basta: sotto un cielo chiaro l'intera ROI la
    supera, le bande si fondono in una sola e il sottotitolo sparisce. Misurato
    su frame sintetici, succede da luminanza di fondo 120 in su.

    Il testo di gioco pero' e' bordato di nero, quindi il fondo *locale* sotto un
    glifo e' scuro qualunque cosa ci sia dietro. Togliendo una stima del fondo
    locale (media su una finestra larga) il limite si sposta a 180, al costo di
    ~0,7 ms per frame.

    **Limite noto**, da sciogliere sulla registrazione vera: testo piu' scuro di
    cio' che lo circonda — una riga grigia su una scena molto chiara — non viene
    trovato, perche' questo operatore cerca il chiaro sullo scuro. Quanto sia un
    caso reale in GTA V lo dice il video, non un frame inventato: fino ad allora
    e' una supposizione da non ottimizzare.
    """
    absolute = luma > cfg.grey_min_luma
    if not cfg.use_local_contrast:
        return absolute
    try:
        import cv2
    except ImportError:  # pragma: no cover - opencv assente
        return absolute
    k = max(3, int(cfg.contrast_kernel) | 1)  # dispari
    background = cv2.blur(luma, (k, k))
    return absolute & ((luma - background) > cfg.contrast_min)


def classify_lines(roi: np.ndarray, cfg: VisionConfig) -> list[LineBand]:
    """Trova le righe nella ROI e assegna a ciascuna la sua classe cromatica.

    Il corpo del glifo si misura con un **percentile alto** della luminanza, non
    con la mediana: il testo di gioco e' antialiasato e bordato di nero, quindi
    la maschera di un testo bianco contiene molti pixel di bordo scuri che
    tirerebbero la mediana verso il basso fino a confondere il bianco col
    grigio. Il 90esimo percentile guarda il cuore delle lettere, che e' la cosa
    che davvero distingue le due classi.
    """
    luma, sat = luma_sat(roi)
    mask = text_mask(luma, cfg)
    if not mask.any():
        return []

    min_px = max(1, int(roi.shape[1] * cfg.min_line_fill))
    out: list[LineBand] = []
    for top, bottom in find_bands(mask, cfg.min_line_height, min_px):
        band_mask = mask[top : bottom + 1]
        if not band_mask.any():
            continue
        band_luma = luma[top : bottom + 1][band_mask]
        band_sat = sat[top : bottom + 1][band_mask]

        body_luma = float(np.percentile(band_luma, cfg.luma_percentile))
        # Anche la saturazione va presa su un percentile alto: un singolo pixel
        # colorato di bordo non deve poter squalificare una riga di dialogo.
        peak_sat = float(np.percentile(band_sat, cfg.sat_percentile))

        if peak_sat > cfg.sat_max:
            cls = LineClass.COLORED
        elif body_luma >= cfg.white_min_luma:
            cls = LineClass.WHITE
        else:
            cls = LineClass.GREY

        cols = np.where(band_mask.any(axis=0))[0]
        x0, x1 = (int(cols[0]), int(cols[-1]) + 1) if cols.size else (0, roi.shape[1])
        band_grey = luma[top : bottom + 1, x0:x1] * band_mask[:, x0:x1]
        out.append(
            LineBand(
                top=int(top),
                bottom=int(bottom),
                cls=cls,
                luma=body_luma,
                sat=peak_sat,
                crop=np.clip(band_grey, 0, 255).astype(np.uint8),
                x0=x0,
                x1=x1,
            )
        )
    return out
