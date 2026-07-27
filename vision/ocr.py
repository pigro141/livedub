"""Riconoscimento dei caratteri sulle righe gia' segmentate.

**Solo recognition, mai detection.** La ROI e' fissa e le righe le ha gia'
trovate `lines.classify_lines` con una proiezione orizzontale che costa
microsecondi. Far girare anche il modello di detection sarebbe rifare da capo
un lavoro gia' fatto, e costa quasi cinquanta volte tanto.

Le regole qui sotto non sono preferenze, sono misure fatte su righe italiane
sintetiche (Arial bold, bordo nero, come i sottotitoli di gioco):

    900 px di larghezza con il testo che ne occupa 350   CER  5.6%   125 ms
    ritaglio stretto sul testo                           CER  0.0%    15 ms

Il modello di default di RapidOCR e' addestrato su cinese+inglese, e la prima
prova sembrava dire che sull'italiano non ce la faceva. Non era vero: gli si
stava dando un'immagine per tre quarti vuota, che il rescaling interno
comprimeva fino a rendere illeggibili le lettere. Con il ritaglio giusto
l'italiano esce perfetto, punteggiatura e accenti compresi. **Ritagliare stretto
non e' un'ottimizzazione, e' un requisito di correttezza.**

Corollario: a 15 ms per riga la CPU basta e avanza, e la GPU resta libera per il
gioco.
"""

from __future__ import annotations

from typing import Protocol

import numpy as np

# Altezza a cui il riconoscitore lavora meglio. Sopra non migliora e la larghezza
# del tensore — che e' cio' che detta il costo — cresce inutilmente.
TARGET_HEIGHT = 48
PAD = 4


class OcrBackend(Protocol):
    name: str

    def read(self, line: np.ndarray) -> tuple[str, float]:
        """Legge una riga gia' ritagliata. Restituisce (testo, confidenza)."""
        ...


def prepare(mask: np.ndarray) -> np.ndarray:
    """Porta una maschera binaria di riga nella forma che il modello vuole.

    Ingresso: uint8 2-D (0/255), gia' stretto sul testo. Uscita: 3 canali, con
    un margine nero e altezza vicina a `TARGET_HEIGHT`.
    """
    if mask.ndim == 3:
        mask = mask[:, :, :3].astype(np.float32).mean(axis=2).astype(np.uint8)
    if mask.size == 0 or mask.shape[0] == 0 or mask.shape[1] == 0:
        return np.zeros((TARGET_HEIGHT, TARGET_HEIGHT, 3), dtype=np.uint8)

    padded = np.pad(mask, ((PAD, PAD), (PAD, PAD)), mode="constant", constant_values=0)

    h = padded.shape[0]
    if h < TARGET_HEIGHT:
        import cv2

        scale = TARGET_HEIGHT / h
        padded = cv2.resize(
            padded,
            (max(1, int(round(padded.shape[1] * scale))), TARGET_HEIGHT),
            interpolation=cv2.INTER_CUBIC,
        )
    return np.stack([padded] * 3, axis=2)


class NullOcr:
    """Non legge niente. Serve ai test e ai gruppi della suite che non devono
    scaricare modelli."""

    name = "null"

    def read(self, line: np.ndarray) -> tuple[str, float]:
        return "", 0.0


class EchoOcr:
    """Restituisce un testo deciso in anticipo, uno per chiamata.

    Con questo il resto della catena (stabilizzatore, fusione, sintesi) si puo'
    verificare su testi noti senza dipendere da cosa il riconoscitore vede
    davvero. Separa i fallimenti dell'OCR da quelli di tutto il resto.
    """

    name = "echo"

    def __init__(self, texts: list[str] | None = None, conf: float = 1.0) -> None:
        self.texts = list(texts or [])
        self.conf = conf
        self.calls = 0

    def read(self, line: np.ndarray) -> tuple[str, float]:
        text = self.texts[self.calls % len(self.texts)] if self.texts else ""
        self.calls += 1
        return text, self.conf


class RapidOcr:
    """RapidOCR (PP-OCR convertito in ONNX) in sola recognition."""

    name = "rapidocr"

    def __init__(self, device: str = "cpu") -> None:
        try:
            from rapidocr_onnxruntime import RapidOCR
        except ImportError as e:  # pragma: no cover - dipende dall'ambiente
            raise RuntimeError(
                "rapidocr-onnxruntime non installato: "
                "`.\\.venv\\Scripts\\python.exe -m pip install rapidocr-onnxruntime`"
            ) from e
        self._engine = RapidOCR()
        self.device = device
        # Prima chiamata: carica i pesi e costruisce le sessioni ONNX. Un secondo
        # abbondante che non deve capitare sulla prima battuta di una partita.
        self._engine(
            np.zeros((TARGET_HEIGHT, TARGET_HEIGHT * 4, 3), np.uint8),
            use_det=False,
            use_cls=False,
            use_rec=True,
        )

    def read(self, line: np.ndarray) -> tuple[str, float]:
        img = prepare(line)
        result, _ = self._engine(img, use_det=False, use_cls=False, use_rec=True)
        if not result:
            return "", 0.0
        text, conf = result[0][0], result[0][1]
        return str(text).strip(), float(conf)


def make_ocr(backend: str, device: str = "cpu") -> OcrBackend:
    """Costruisce il backend richiesto.

    Un nome sconosciuto e' un errore: un refuso in config non deve tradursi in
    un doppiaggio muto senza spiegazione.
    """
    if backend in ("rapidocr", "ppocr"):
        return RapidOcr(device=device)
    if backend in ("none", "null"):
        return NullOcr()
    if backend == "echo":
        return EchoOcr()
    raise ValueError(f"backend OCR sconosciuto: {backend!r}")
