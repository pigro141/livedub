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

**Il costo dipende dalla larghezza, non dall'altezza.** Misurato al variare
della lunghezza della battuta:

    5 caratteri  ->   67 px  ->   8 ms
   34 caratteri  ->  514 px  ->  17 ms
   60 caratteri  ->  868 px  ->  31 ms
   94 caratteri  -> 1346 px  ->  59 ms

Da qui una conseguenza controintuitiva: **riscalare in altezza fa male**. Portare
una riga a 48 px la allarga in proporzione, e su una battuta lunga il costo
raddoppia (120 ms invece di 59) senza guadagnare un decimale di accuratezza — il
CER e' identico a 48 px, a 32 px e all'altezza nativa. Si riscala solo quando la
riga e' davvero piccola, sotto i 20 px, dove qualcosa si guadagna.

La CPU basta e avanza, e la GPU resta libera per il gioco.
"""

from __future__ import annotations

import unicodedata
from typing import Protocol

import numpy as np

# Sotto questa altezza il riconoscitore inizia a perdere colpi e conviene
# ingrandire; sopra, ingrandire costa e basta.
MIN_HEIGHT = 20
TARGET_HEIGHT = 32
PAD = 4

# Punteggiatura che ha senso in una battuta italiana, e che al sintetizzatore
# serve: il punto interrogativo e l'esclamativo cambiano l'intonazione, la
# virgola mette la pausa. Si tiene, non si butta.
#
# **I simboli no.** `/ & + = * @ #` erano in questa lista sotto la stessa
# etichetta, ma nessuno di loro cambia l'intonazione di niente: il
# sintetizzatore li legge come *parole* — `'Va bene.../'` usciva dalla bocca di
# Piper come "va bene barra". E sono precisamente gli artefatti che l'OCR
# produce qui, dove un tratto spezzato o il bordo di un oggetto di scena diventa
# un `+`: `'r ilii-+il'`, `'rnri biit+n a'`. Un glifo inventato che viene
# *pronunciato* e' peggio di uno scartato.
#
# `% € $` restano: in GTA V si parla di soldi, e li' la cifra e' la battuta.
PUNTEGGIATURA = set(" .,;:!?'\"()[]-–—…«»‘’“”%€$")


def italian_only(text: str) -> str:
    """Toglie cio' che non puo' far parte di una battuta italiana.

    Il riconoscitore di default e' addestrato su **cinese e inglese**, e su una
    banda di scenario restituisce volentieri glifi CJK: `'冏一'`, `'一..uuA'`,
    `'/一一'`. Finivano in bocca al sintetizzatore, che provava a pronunciarli.

    Il filtro sulla lingua c'era gia' — `min_ocr_chars` — ma contava i caratteri
    **alfanumerici**, e in Python `'冏'.isalnum()` e' `True`. Il cancello era
    scritto per fermare esattamente questo e lo lasciava passare, che e' il tipo
    di difetto che sopravvive proprio perche' sembra gia' risolto.

    Si tengono le lettere latine (accenti compresi: `NFD` separa il segno dalla
    lettera, e si guarda la lettera), le cifre e la punteggiatura che serve alla
    prosodia. Tutto il resto sparisce.
    """
    fuori = []
    for ch in text:
        if ch in PUNTEGGIATURA or ch.isdigit():
            fuori.append(ch)
            continue
        if not ch.isalpha():
            continue
        base = unicodedata.normalize("NFD", ch)[0]
        if "a" <= base.lower() <= "z":
            fuori.append(ch)
    return _senza_bordi(" ".join("".join(fuori).split()))


def _senza_bordi(text: str) -> str:
    """Toglie i gruppi di sola punteggiatura in testa e in coda.

    Nascono dal bordo del riquadro: allargandolo per non tagliare le battute
    lunghe, entrano anche gli oggetti di scena ai due lati, e cio' che l'OCR ne
    ricava finisce **attaccato alla frase** — `'-- :- Pero devo dirglielo'`,
    `'. obbligato a parlare'`. In mezzo alla frase un segno spurio e' un
    inciampo; in testa e' la prima cosa che il sintetizzatore pronuncia, cioe'
    la parte della battuta su cui l'orecchio decide se ha capito.

    Si tolgono solo i gruppi **senza nessuna lettera e nessuna cifra**: un
    `'...'` iniziale se ne va con loro, e si perde una sfumatura di prosodia.
    E' il prezzo, ed e' piccolo rispetto a una battuta che comincia con "meno
    meno due punti".
    """
    parole = text.split()
    while parole and not any(ch.isalnum() for ch in parole[0]):
        parole.pop(0)
    while parole and not any(ch.isalnum() for ch in parole[-1]):
        parole.pop()
    return " ".join(parole)


def latin_letters(text: str) -> int:
    """Quante lettere o cifre **latine** contiene. E' il conto che
    `min_ocr_chars` intendeva fare fin dall'inizio."""
    return sum(1 for ch in italian_only(text) if ch.isalnum())


class OcrBackend(Protocol):
    name: str

    def read(self, line: np.ndarray) -> tuple[str, float]:
        """Legge una riga gia' ritagliata. Restituisce (testo, confidenza)."""
        ...


def prepare(mask: np.ndarray) -> np.ndarray:
    """Porta una maschera binaria di riga nella forma che il modello vuole.

    Ingresso: uint8 2-D (0/255), gia' stretto sul testo. Uscita: 3 canali con un
    margine nero, ingrandita **solo se serve** — vedi la nota sul costo in cima
    al modulo: allargare il tensore per nulla e' il modo piu' facile di
    raddoppiare la latenza dell'OCR.
    """
    if mask.ndim == 3:
        mask = mask[:, :, :3].astype(np.float32).mean(axis=2).astype(np.uint8)
    if mask.size == 0 or mask.shape[0] == 0 or mask.shape[1] == 0:
        return np.zeros((TARGET_HEIGHT, TARGET_HEIGHT, 3), dtype=np.uint8)

    padded = np.pad(mask, ((PAD, PAD), (PAD, PAD)), mode="constant", constant_values=0)

    if padded.shape[0] < MIN_HEIGHT:
        import cv2

        scale = TARGET_HEIGHT / padded.shape[0]
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
