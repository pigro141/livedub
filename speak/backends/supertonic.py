"""Backend SuperTonic 3: dieci voci italiane invece di due.

Il piano dichiarava che le due voci italiane di Piper erano il tetto del tier A
e che per superarlo serviva la GPU (F6, Qwen3-TTS). SuperTonic 3 lo supera
restando su CPU e in ONNX: **cinque voci maschili e cinque femminili** native,
senza trucchi di pitch. Per F3 — voci diverse per personaggi diversi — e' la
differenza fra poter assegnare e dover riciclare.

Misurato su questa macchina, italiano, contro Piper:

    modello                    RTF     sintesi di una battuta da 2,4 s
    Piper riccardo x_low      0,026    ~60 ms
    SuperTonic 3, 4 passi     0,095    ~230 ms
    SuperTonic 3, 8 passi     0,17     ~410 ms

Il costo e' reale e non e' in streaming: la battuta si sintetizza intera, quindi
la latenza cresce con la sua lunghezza. Quattro passi di diffusione bastano —
otto costano il doppio e la differenza va giudicata a orecchio, non a occhio.

**La velocita' non e' un gusto, e' una misura.** A `speed` 1,05 la stessa frase
dura il 47% piu' che con Piper, il cui ritmo all'ascolto era gia' giusto.
Misurato su quattro battute vere: Piper fa 17,4 caratteri al secondo, e
SuperTonic li pareggia a **speed 1,50** (17,1 car/s, scarto +2%). Da qui il
default: non un numero scelto perche' suona bene, ma quello che allinea il
ritmo a un riferimento verificato.

I modelli (~398 MB) finiscono nella cache di SuperTonic, non in `models/`: li
gestisce il pacchetto e non ha senso duplicarli.
"""

from __future__ import annotations

import time

import numpy as np

from core.types import VoiceSpec
from mix.stretch import pitch_shift, resample
from speak.base import Speech

# Frequenza nativa del vocoder.
NATIVE_RATE = 44100

# Le dieci voci preimpostate. I nomi sono quelli dei file di stile del modello.
VOICES = {
    "supertonic-M1": ("M1", "m"),
    "supertonic-M2": ("M2", "m"),
    "supertonic-M3": ("M3", "m"),
    "supertonic-M4": ("M4", "m"),
    "supertonic-M5": ("M5", "m"),
    "supertonic-F1": ("F1", "f"),
    "supertonic-F2": ("F2", "f"),
    "supertonic-F3": ("F3", "f"),
    "supertonic-F4": ("F4", "f"),
    "supertonic-F5": ("F5", "f"),
}

# Ritmo pareggiato a Piper: si veda il docstring del modulo.
DEFAULT_SPEED = 1.50


class SupertonicTts:
    """Sintesi SuperTonic 3, con gli stili caricati su richiesta."""

    name = "supertonic"

    def __init__(
        self,
        samplerate: int = 22050,
        steps: int = 4,
        speed: float = DEFAULT_SPEED,
        download: bool = True,
    ) -> None:
        self.samplerate = samplerate
        self.steps = max(1, int(steps))
        self.speed = float(speed)
        self.download = download
        self._tts = None
        self._styles: dict[str, object] = {}

    # -- caricamento -------------------------------------------------------

    def _engine(self):
        if self._tts is None:
            try:
                import supertonic
            except ImportError as e:  # pragma: no cover - dipende dall'ambiente
                raise RuntimeError(
                    "supertonic non installato: "
                    "`.\\.venv\\Scripts\\python.exe -m pip install supertonic`"
                ) from e
            self._tts = supertonic.TTS(auto_download=self.download)
        return self._tts

    def _style(self, base_voice: str):
        cached = self._styles.get(base_voice)
        if cached is not None:
            return cached
        nome = VOICES.get(base_voice, (None, None))[0]
        if nome is None:
            raise ValueError(
                f"voce SuperTonic sconosciuta: {base_voice!r} (note: {sorted(VOICES)})"
            )
        style = self._engine().get_voice_style(nome)
        self._styles[base_voice] = style
        return style

    def preload(self, names: list[str]) -> None:
        """Carica in anticipo. Il primo `synthesize` costruisce le sessioni ONNX
        e paga tutto il caricamento: non deve capitare sulla prima battuta."""
        for n in names:
            try:
                self._style(n)
            except Exception:
                pass

    # -- sintesi -----------------------------------------------------------

    def synthesize(self, text: str, voice: VoiceSpec, rate: float = 1.0) -> Speech:
        text = text.strip()
        if not text:
            return Speech(np.zeros(0, np.float32), self.samplerate, voice.voice_id, text=text)

        style = self._style(voice.base_voice)
        # `rate` e' la correzione del tempo chiesta dalla catena, `voice.rate` il
        # carattere della voce, `self.speed` il ritmo di base pareggiato a Piper.
        # Si moltiplicano: sono tre cose diverse che parlano tutte di velocita'.
        effective = max(0.1, self.speed * rate * voice.rate)

        t0 = time.perf_counter()
        wav, _ = self._engine().synthesize(
            text, style, total_steps=self.steps, speed=effective, lang="it"
        )
        total_ms = (time.perf_counter() - t0) * 1000.0

        audio = np.asarray(wav, dtype=np.float32).reshape(-1)
        if audio.size and voice.semitones:
            audio = pitch_shift(audio, voice.semitones, samplerate=NATIVE_RATE)
        if NATIVE_RATE != self.samplerate:
            audio = resample(audio, NATIVE_RATE, self.samplerate)

        return Speech(
            audio=audio,
            samplerate=self.samplerate,
            voice_id=voice.voice_id,
            # Non c'e' streaming: il primo campione esiste quando esiste tutto.
            # Dichiararlo pari al totale e' l'unica cosa onesta — riportare un
            # numero piccolo qui farebbe sembrare la latenza migliore di com'e'.
            first_sample_ms=total_ms,
            total_ms=total_ms,
            text=text,
        )
