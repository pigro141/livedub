"""Frame di sottotitoli sintetici, con colori noti.

Servono a verificare il classificatore di righe *prima* di vederlo su un frame
vero. Un classificatore sbagliato non da' errore: da' un doppiaggio che legge i
suggerimenti a voce alta o che scambia due personaggi. L'unico modo di
accorgersene in anticipo e' costruire l'ingresso di cui si conosce gia' la
risposta.

Il testo e' renderizzato davvero, con font e bordo nero come nei sottotitoli di
gioco, perche' l'antialiasing e' proprio la cosa che rende difficile distinguere
il bianco dal grigio: le barre piatte non metterebbero alla prova niente.
"""

from __future__ import annotations

import numpy as np

# Colori dei sottotitoli. I due grigi sono la coppia che la pipeline deve saper
# separare; il giallo e' il colore dei suggerimenti da scartare.
WHITE = (255, 255, 255)
GREY = (155, 155, 155)
YELLOW = (245, 205, 60)
GREEN = (120, 235, 120)

_FONTS = (
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
    r"C:\Windows\Fonts\arial.ttf",
)


def font_available() -> bool:
    return _load_font(28) is not None


def _load_font(size: int):
    try:
        from PIL import ImageFont
    except ImportError:  # pragma: no cover
        return None
    for path in _FONTS:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return None


def render_subtitles(
    lines: list[tuple[str, tuple[int, int, int]]],
    size: tuple[int, int] = (240, 900),
    font_px: int = 30,
    line_gap: int = 10,
    background: int = 0,
    noise: float = 0.0,
    seed: int = 0,
) -> np.ndarray:
    """Disegna righe di sottotitolo centrate, su fondo scuro.

    `lines` e' una lista di (testo, colore). Restituisce un array uint8 RGB —
    ma vale la pena ricordare che il classificatore da' lo stesso risultato in
    BGR, per costruzione.
    """
    from PIL import Image, ImageDraw

    h, w = size
    rng = np.random.default_rng(seed)
    base = np.full((h, w, 3), background, dtype=np.uint8)
    if noise > 0:
        wobble = rng.normal(0.0, noise * 255.0, (h, w, 3))
        base = np.clip(base.astype(np.float32) + wobble, 0, 255).astype(np.uint8)

    img = Image.fromarray(base)
    draw = ImageDraw.Draw(img)
    font = _load_font(font_px)
    if font is None:  # pragma: no cover - solo se mancano i font di sistema
        raise RuntimeError("nessun font di sistema disponibile per il rendering")

    y = line_gap
    for text, colour in lines:
        box = draw.textbbox((0, 0), text, font=font)
        tw = box[2] - box[0]
        x = max(0, (w - tw) // 2 - box[0])
        # Bordo nero, come nei sottotitoli di gioco: e' quello che crea i pixel
        # di transizione che falserebbero una mediana.
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2), (-2, 2), (2, -2)):
            draw.text((x + dx, y - box[1] + dy), text, font=font, fill=(0, 0, 0))
        draw.text((x, y - box[1]), text, font=font, fill=colour)
        y += (box[3] - box[1]) + line_gap + 6

    return np.array(img)


def frame_with_roi(
    lines: list[tuple[str, tuple[int, int, int]]],
    frame_size: tuple[int, int] = (1080, 1920),
    roi: tuple[float, float, float, float] = (0.15, 0.72, 0.70, 0.22),
    **kw,
) -> np.ndarray:
    """Frame intero con i sottotitoli piazzati dentro la ROI indicata."""
    fh, fw = frame_size
    x0 = int(round(roi[0] * fw))
    y0 = int(round(roi[1] * fh))
    rw = int(round(roi[2] * fw))
    rh = int(round(roi[3] * fh))
    frame = np.zeros((fh, fw, 3), dtype=np.uint8)
    frame[y0 : y0 + rh, x0 : x0 + rw] = render_subtitles(lines, size=(rh, rw), **kw)
    return frame


def empty_frame(
    frame_size: tuple[int, int] = (1080, 1920), background: int = 0
) -> np.ndarray:
    return np.full((*frame_size, 3), background, dtype=np.uint8)
