"""Le sorgenti del banco di prova: da dove arrivano frame e audio.

Il runner (`tools/replay.py`) non sa da dove vengono i pacchetti, e questa e' la
ragione per cui esiste questo modulo separato. Una sorgente sintetica e una
registrazione vera devono essere intercambiabili, altrimenti la misura fatta sul
finto e quella fatta sul vero non sono confrontabili — e il confronto fra le due
e' esattamente il modo di distinguere *codice rotto* da *segnale inutilizzabile*.

    SyntheticSource   sottotitoli disegnati, colori noti, risposta gia' nota
    VideoSource       la registrazione dello schermo, con i suoi problemi veri

**La sorgente video non ha ancora la traccia audio.** OpenCV decodifica solo
l'immagine, e nell'ambiente non c'e' ffmpeg. Per la fase del tempo serve prima
la durata dei sottotitoli, che e' informazione puramente video; l'onset dal VAD
arriva quando ci sara' un modo di estrarre la traccia. Meglio una sorgente che
dichiara di non avere audio che una che ne inventa.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Protocol

import numpy as np


@dataclass(slots=True)
class Packet:
    """Un istante della sorgente: un frame video, un blocco audio, o entrambi."""

    t: float
    frame: np.ndarray | None = None
    audio: np.ndarray | None = None


class Source(Protocol):
    fps: float
    samplerate: int

    def packets(self) -> Iterator[Packet]:
        ...


# -- sorgente sintetica ----------------------------------------------------


@dataclass
class SyntheticSource:
    """Sorgente finta ma deterministica.

    Disegna sottotitoli sintetici nella ROI secondo la grammatica reale (righe
    bianche, righe grigie, righe colorate da scartare) e produce un audio con
    raffiche di parlato finto. Non e' un gioco, ma esercita esattamente le
    strade che il video vero esercitera'.
    """

    seconds: float = 10.0
    fps: float = 30.0
    samplerate: int = 48000
    size: tuple[int, int] = (180, 640)  # altezza, larghezza della ROI
    seed: int = 0
    subtitle_every: float = 2.5
    subtitle_hold: float = 1.8

    def packets(self) -> Iterator[Packet]:
        rng = np.random.default_rng(self.seed)
        h, w = self.size
        n_frames = int(self.seconds * self.fps)
        spf = 1.0 / self.fps
        samples_per_frame = int(round(self.samplerate * spf))

        for i in range(n_frames):
            t = i * spf
            phase = t % self.subtitle_every
            visible = phase < self.subtitle_hold
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            if visible:
                cycle = int(t // self.subtitle_every)
                _draw_line(frame, row=40, luma=235, text_width=int(w * 0.6))
                if cycle % 3 == 1:  # ogni tanto un secondo speaker in grigio
                    _draw_line(frame, row=80, luma=150, text_width=int(w * 0.4))
                if cycle % 4 == 3:  # ogni tanto un suggerimento colorato
                    _draw_line(frame, row=120, luma=210, text_width=int(w * 0.3), hue=(240, 200, 40))

            # Audio: raffica di parlato finto mentre il sottotitolo e' a schermo.
            base = np.zeros(samples_per_frame, dtype=np.float32)
            if visible:
                tt = np.arange(samples_per_frame, dtype=np.float32) / self.samplerate + t
                f0 = 110.0 + 40.0 * ((int(t // self.subtitle_every)) % 3)
                base = (0.25 * np.sin(2 * np.pi * f0 * tt)).astype(np.float32)
                base += (0.02 * rng.standard_normal(samples_per_frame)).astype(np.float32)
            yield Packet(t=t, frame=frame, audio=base)


def _draw_line(frame: np.ndarray, row: int, luma: int, text_width: int, hue=None) -> None:
    """Disegna una barra che imita una riga di testo. Non serve che assomigli a
    delle lettere: serve che abbia la luminanza e la saturazione giuste."""
    h, w, _ = frame.shape
    x0 = (w - text_width) // 2
    colour = np.array(hue if hue is not None else (luma, luma, luma), dtype=np.uint8)
    frame[row : row + 16, x0 : x0 + text_width] = colour


# -- sorgente video --------------------------------------------------------


@dataclass(frozen=True, slots=True)
class VideoInfo:
    """Cosa dice il file prima di aprirlo davvero."""

    path: Path
    width: int
    height: int
    src_fps: float
    n_frames: int

    @property
    def duration(self) -> float:
        return self.n_frames / self.src_fps if self.src_fps > 0 else 0.0

    def __str__(self) -> str:
        return (
            f"{self.path.name}: {self.width}x{self.height} @ {self.src_fps:.3f} fps, "
            f"{self.n_frames} frame ({self.duration / 60:.1f} min)"
        )


def probe(path: str | Path) -> VideoInfo:
    """Legge le proprieta' del file senza decodificarlo."""
    import cv2

    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"registrazione non trovata: {p}")
    cap = cv2.VideoCapture(str(p))
    try:
        if not cap.isOpened():
            raise RuntimeError(f"OpenCV non riesce ad aprire {p}")
        return VideoInfo(
            path=p,
            width=int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
            height=int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
            src_fps=float(cap.get(cv2.CAP_PROP_FPS)),
            n_frames=int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),
        )
    finally:
        cap.release()


class VideoSource:
    """La registrazione dello schermo come sorgente del banco.

    Tre scelte che vale la pena spiegare, perche' ognuna ha un'alternativa
    ovvia e sbagliata:

    - **il tempo viene dal conteggio dei frame, non dall'orologio del file.**
      `t = indice / fps_sorgente`. Chiedere a OpenCV la posizione in
      millisecondi sarebbe piu' diretto e meno affidabile: su un file H.264 quel
      valore dipende dai timestamp del contenitore, e due esecuzioni dello
      stesso file possono darlo diverso. Il conteggio no, e il determinismo del
      banco e' la proprieta' su cui poggia ogni confronto prima/dopo;

    - **si decima con `grab()`, non con `read()`.** Una registrazione a 60 fps
      data in pasto a una pipeline che gira a 30 ha meta' dei frame di troppo.
      `grab()` avanza nello stream senza convertire il frame in array: sui
      frame che si buttano si paga la decodifica ma non la conversione, che su
      1080p e' la parte cara;

    - **i colori restano BGR.** `vision/lines.py` classifica con luminanza
      (media sui canali) e saturazione (max meno min): entrambe simmetriche
      rispetto all'ordine dei canali. Convertire costerebbe una copia per frame
      per non cambiare nessun risultato.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        fps: float = 30.0,
        start: float = 0.0,
        end: float | None = None,
        samplerate: int = 48000,
    ) -> None:
        self.info = probe(path)
        if self.info.src_fps <= 0:
            raise RuntimeError(f"frame rate non leggibile da {self.info.path}")
        self.samplerate = samplerate
        self.start = max(0.0, float(start))
        self.end = float(end) if end is not None else None
        # Un solo frame ogni `step`: il rapporto e' intero perche' saltare
        # frazioni di frame introdurrebbe un jitter che poi si scambierebbe per
        # rumore della misura.
        self.step = max(1, int(round(self.info.src_fps / max(1e-6, fps))))
        self.fps = self.info.src_fps / self.step

    @property
    def has_audio(self) -> bool:
        """OpenCV non decodifica l'audio. Dichiararlo evita che qualcuno legga
        il silenzio come "il gioco non stava parlando"."""
        return False

    def packets(self) -> Iterator[Packet]:
        import cv2

        cap = cv2.VideoCapture(str(self.info.path))
        try:
            if not cap.isOpened():
                raise RuntimeError(f"OpenCV non riesce ad aprire {self.info.path}")

            index = 0
            if self.start > 0:
                index = int(round(self.start * self.info.src_fps))
                cap.set(cv2.CAP_PROP_POS_FRAMES, index)
                # Il seek su H.264 atterra sul keyframe piu' vicino, quindi la
                # posizione vera puo' non essere quella chiesta: si prende
                # quella vera, altrimenti tutti i timestamp sarebbero sfalsati.
                index = int(cap.get(cv2.CAP_PROP_POS_FRAMES))

            last = int(round(self.end * self.info.src_fps)) if self.end is not None else None
            while last is None or index <= last:
                ok = cap.grab()
                if not ok:
                    break
                if (index % self.step) == 0:
                    ok, frame = cap.retrieve()
                    if not ok:
                        break
                    yield Packet(t=index / self.info.src_fps, frame=frame, audio=None)
                index += 1
        finally:
            cap.release()
