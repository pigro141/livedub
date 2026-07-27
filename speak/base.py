"""Interfaccia della sintesi.

Un backend riceve un testo e una voce e restituisce audio. Tutto quello che
riguarda *quanto in fretta* parlare, *con che intonazione* e *quanto forte* e'
gia' stato deciso a monte e arriva dentro la `VoiceSpec` e il parametro `rate`:
il backend non prende decisioni artistiche, esegue.

La separazione serve a poter cambiare motore senza toccare nient'altro. Il tier
A (Piper, CPU, latenza garantita) e il tier B (un modello espressivo su GPU)
devono essere intercambiabili da configurazione, perche' quale dei due convenga
si decide sul banco e non a priori.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from core.types import VoiceSpec


@dataclass(slots=True)
class Speech:
    """Audio sintetizzato, con il conto di quanto e' costato produrlo."""

    audio: np.ndarray  # float32 mono in [-1, 1]
    samplerate: int
    voice_id: str = "?"
    first_sample_ms: float = 0.0  # tempo al primo campione: e' la latenza che si sente
    total_ms: float = 0.0
    text: str = ""

    @property
    def duration(self) -> float:
        return len(self.audio) / float(self.samplerate) if self.samplerate else 0.0

    @property
    def rtf(self) -> float:
        """Real-time factor: sotto 1 vuol dire che si sintetizza piu' in fretta
        di quanto si ascolta."""
        d = self.duration
        return (self.total_ms / 1000.0) / d if d > 0 else 0.0


class TtsBackend(Protocol):
    name: str
    samplerate: int

    def synthesize(self, text: str, voice: VoiceSpec, rate: float = 1.0) -> Speech:
        ...


@dataclass
class ToneTts:
    """Backend finto: produce un bip modulato invece di parlare.

    Non e' un segnaposto inutile. Serve a misurare **tutto il resto** della
    catena — tempi, scheduler, mixer, duck — senza che i tempi del sintetizzatore
    vero si mescolino ai loro, e senza scaricare un modello. Se una battuta arriva
    tardi con questo backend, il colpevole non e' il TTS.

    La durata imita quella del parlato (circa 14 caratteri al secondo) e
    l'intonazione segue la voce, cosi' anche l'assegnazione delle voci si sente.
    """

    name: str = "tone"
    samplerate: int = 22050
    chars_per_second: float = 14.0

    def synthesize(self, text: str, voice: VoiceSpec, rate: float = 1.0) -> Speech:
        import time

        t0 = time.perf_counter()
        rate = max(0.1, rate * voice.rate)
        seconds = max(0.15, len(text) / self.chars_per_second / rate)
        n = int(seconds * self.samplerate)
        t = np.arange(n, dtype=np.float32) / self.samplerate

        base_f0 = 190.0 if voice.gender == "f" else 115.0
        f0 = base_f0 * (2.0 ** (voice.semitones / 12.0))
        # Poche armoniche e un inviluppo a sillabe: basta a distinguere le voci
        # a orecchio senza fingere di essere parlato.
        wave = sum(
            (0.6 / k) * np.sin(2 * np.pi * f0 * k * t) for k in (1, 2, 3)
        ).astype(np.float32)
        syllables = 0.55 + 0.45 * np.sin(2 * np.pi * 4.0 * rate * t)
        fade = np.minimum(1.0, np.minimum(t, seconds - t) * 40.0).clip(0.0)
        audio = (wave * syllables * fade * 0.25).astype(np.float32)

        ms = (time.perf_counter() - t0) * 1000.0
        return Speech(
            audio=audio,
            samplerate=self.samplerate,
            voice_id=voice.voice_id,
            first_sample_ms=ms,
            total_ms=ms,
            text=text,
        )


@dataclass
class SilentTts:
    """Non produce nulla. Per i test che vogliono la catena senza audio."""

    name: str = "silent"
    samplerate: int = 22050

    def synthesize(self, text: str, voice: VoiceSpec, rate: float = 1.0) -> Speech:
        return Speech(
            audio=np.zeros(0, np.float32),
            samplerate=self.samplerate,
            voice_id=voice.voice_id,
            text=text,
        )
