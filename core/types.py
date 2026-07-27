"""Tipi che attraversano la pipeline.

Sono deliberatamente pochi e immutabili dove possibile: sono il contratto fra i
due domini (video e audio) e il punto in cui si incontrano. Ogni evento porta
con se' i propri tempi, perche' la fusione e' un problema temporale e un evento
senza timestamp non serve a niente.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from enum import Enum
from typing import Any, Sequence

import numpy as np


class LineClass(Enum):
    """Classe cromatica di una riga di sottotitolo.

    Il colore in GTA V non e' decorativo, e' grammatica:

    - `WHITE`   battuta dello speaker principale, da leggere;
    - `GREY`    battuta di un *secondo* speaker che parla quasi in contemporanea:
                da leggere, ma come battuta separata e con un'altra voce;
    - `COLORED` la riga contiene glifi saturi (giallo, verde, blu): non e'
                dialogo ma un suggerimento o un obiettivo. **Si scarta la riga
                intera**, non solo la parola colorata.
    """

    WHITE = "white"
    GREY = "grey"
    COLORED = "colored"

    @property
    def is_dialogue(self) -> bool:
        return self is not LineClass.COLORED


@dataclass(frozen=True, slots=True)
class OcrLine:
    """Una riga di testo letta dalla ROI, prima di diventare una battuta."""

    text: str
    cls: LineClass
    bbox: tuple[int, int, int, int]  # x, y, w, h dentro la ROI
    luma: float = 0.0  # luminanza mediana dei pixel di testo, 0-255
    sat: float = 0.0  # saturazione massima trovata sulla riga, 0-255
    conf: float = 1.0

    @property
    def top(self) -> int:
        return self.bbox[1]


@dataclass(frozen=True, slots=True)
class SubtitleEvent:
    """Una battuta letta dallo schermo: il *cosa* si dice.

    Nasce da una o piu' `OcrLine` della **stessa** classe cromatica: righe con
    la stessa luminanza sono una frase andata a capo, righe con luminanza
    diversa sono due battute distinte e generano due eventi.
    """

    text: str
    cls: LineClass
    t_on: float
    t_off: float | None = None  # noto solo quando il sottotitolo sparisce
    lines: tuple[OcrLine, ...] = ()

    @property
    def n_chars(self) -> int:
        return len(self.text)

    @property
    def duration(self) -> float | None:
        """Durata reale del sottotitolo a schermo, o None se ancora visibile."""
        return None if self.t_off is None else self.t_off - self.t_on

    def closed(self, t_off: float) -> "SubtitleEvent":
        return replace(self, t_off=t_off)


@dataclass(frozen=True, slots=True)
class Emotion:
    """Come e' detta la battuta.

    `label` e' comoda da leggere nei log, ma la pipeline usa le tre grandezze
    continue: sono quelle che si mappano su velocita', pitch e guadagno senza
    salti fra una battuta e la successiva.
    """

    label: str = "neutral"
    arousal: float = 0.0  # -1 calmo ... +1 acceso
    valence: float = 0.0  # -1 negativo ... +1 positivo
    intensity: float = 0.0  # 0 ... 1, quanto e' marcata
    confidence: float = 0.0

    @staticmethod
    def neutral() -> "Emotion":
        return Emotion()


@dataclass(frozen=True, slots=True)
class SpeakerEvent:
    """Chi parla e come, dedotto dall'audio del gioco.

    `speaker_id` e' un'etichetta interna progressiva (`S0`, `S1`, ...): i
    sottotitoli non contengono nomi, quindi l'identita' e' per costruzione
    relativa e stabile solo dentro la sessione.
    """

    speaker_id: str
    t0: float
    t1: float
    dbfs: float = -60.0
    emotion: Emotion = field(default_factory=Emotion.neutral)
    confidence: float = 0.0
    embedding: np.ndarray | None = None
    is_new: bool = False  # prima volta che si sente questa voce

    @property
    def duration(self) -> float:
        return self.t1 - self.t0


@dataclass(frozen=True, slots=True)
class VoiceSpec:
    """Una voce del pool.

    Il pool italiano di base e' piccolo, quindi una voce non e' solo un modello
    ma un modello *piu'* una trasformazione: due varianti di pitch della stessa
    voce Piper sono due voci distinte agli effetti dell'assegnazione.
    """

    voice_id: str
    backend: str
    base_voice: str
    semitones: float = 0.0  # spostamento di pitch applicato in uscita
    rate: float = 1.0  # velocita' di base, moltiplicativa
    gender: str = "?"  # "m", "f", "?" — vincola l'assegnazione quando si sa


@dataclass(frozen=True, slots=True)
class Utterance:
    """Cosa la catena di sintesi deve produrre, gia' deciso da tutti gli stadi
    a monte. E' l'unico oggetto che il TTS vede."""

    text: str
    voice: VoiceSpec
    t_start: float  # quando dovrebbe iniziare a suonare
    budget: float  # secondi disponibili prima della scadenza stimata
    rate: float = 1.0  # velocita' finale, gia' comprensiva di emozione e timing
    semitones: float = 0.0
    gain_db: float = 0.0
    filters: tuple[str, ...] = ()  # es. ("phone",) per la voce al telefono
    speaker_id: str = "?"
    emotion: Emotion = field(default_factory=Emotion.neutral)
    source: SubtitleEvent | None = None
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AudioChunk:
    """Blocco audio con il tempo del suo primo campione.

    `samples` e' float32 in [-1, 1], shape `(n,)` per il mono e `(n, ch)` per il
    multicanale.
    """

    samples: np.ndarray
    t0: float
    samplerate: int

    @property
    def n_frames(self) -> int:
        return int(self.samples.shape[0])

    @property
    def channels(self) -> int:
        return 1 if self.samples.ndim == 1 else int(self.samples.shape[1])

    @property
    def duration(self) -> float:
        return self.n_frames / float(self.samplerate)

    @property
    def t1(self) -> float:
        return self.t0 + self.duration


def merge_lines(lines: Sequence[OcrLine], t_on: float) -> list[SubtitleEvent]:
    """Raggruppa righe OCR in battute secondo la grammatica dei sottotitoli.

    Le righe colorate spariscono. Le restanti si raggruppano **per classe**
    mantenendo l'ordine verticale: righe consecutive della stessa classe sono
    una frase sola; il cambio di classe apre una nuova battuta.
    """
    ordered = sorted((ln for ln in lines if ln.cls.is_dialogue), key=lambda ln: ln.top)
    events: list[SubtitleEvent] = []
    group: list[OcrLine] = []

    def flush() -> None:
        if not group:
            return
        text = " ".join(ln.text.strip() for ln in group if ln.text.strip())
        if text:
            events.append(SubtitleEvent(text=text, cls=group[0].cls, t_on=t_on, lines=tuple(group)))
        group.clear()

    for line in ordered:
        if group and line.cls is not group[0].cls:
            flush()
        group.append(line)
    flush()
    return events
