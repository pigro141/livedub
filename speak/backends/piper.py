"""Backend Piper: il tier A, quello che deve funzionare sempre.

Misurato su questa macchina (i9-11900K, CPU, nessuna GPU coinvolta):

    voce                    1o campione    RTF
    it_IT-paola-medium       36 - 70 ms    0,033
    it_IT-riccardo-x_low     36 - 56 ms    0,024

Con un budget di ~350 ms dalla comparsa del sottotitolo al primo fonema, e l'OCR
che ne consuma una quindicina, la sintesi non e' il collo di bottiglia — e non
tocca la GPU, quindi non compete con il gioco. E' per questo che e' il default.

**`length_scale` non e' proporzionale.** Chiedendo 0,8 si ottiene un audio lungo
il 14% piu' del previsto; a 1,25 l'errore e' del 6,5%. Va bene per dare un
carattere alla voce (una parlata piu' lenta *suona* diversa da una veloce, non
solo piu' lunga), ma non per centrare una scadenza. Per quello c'e'
`mix.stretch.fit_duration`, che sulla durata e' esatto.

Le due voci hanno frequenze di uscita diverse (22050 e 16000 Hz): il backend
riporta tutto alla frequenza di lavoro, altrimenti il mixer riceverebbe blocchi
incompatibili e il secondo personaggio parlerebbe come un disco andato a rilento.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from core.types import VoiceSpec
from mix.stretch import pitch_shift, resample
from speak.base import Speech

# Dove stanno i modelli e come si chiamano dentro il repo di Rhasspy.
MODELS_DIR = Path(__file__).resolve().parents[2] / "models" / "piper"
REPO = "rhasspy/piper-voices"
KNOWN = {
    "it_IT-paola-medium": "it/it_IT/paola/medium",
    "it_IT-riccardo-x_low": "it/it_IT/riccardo/x_low",
}


def model_path(name: str, download: bool = True) -> Path:
    """Percorso del modello, scaricandolo alla prima richiesta.

    Il download avviene una volta sola e finisce in `models/`, che e'
    gitignorato: sono 28-64 MB per voce, materiale della macchina.
    """
    sub = KNOWN.get(name)
    if sub is None:
        raise ValueError(f"voce Piper sconosciuta: {name!r} (note: {sorted(KNOWN)})")
    local = MODELS_DIR / sub / f"{name}.onnx"
    if local.exists() and local.with_suffix(".onnx.json").exists():
        return local
    if not download:
        raise FileNotFoundError(f"modello non presente: {local}")

    from huggingface_hub import hf_hub_download

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    hf_hub_download(REPO, f"{sub}/{name}.onnx", local_dir=MODELS_DIR)
    hf_hub_download(REPO, f"{sub}/{name}.onnx.json", local_dir=MODELS_DIR)
    return local


class PiperTts:
    """Sintesi Piper con pool di voci caricate su richiesta."""

    name = "piper"

    def __init__(self, samplerate: int = 22050, download: bool = True) -> None:
        self.samplerate = samplerate
        self.download = download
        self._voices: dict[str, object] = {}
        self._native_rate: dict[str, int] = {}

    def preload(self, names: list[str]) -> None:
        """Carica in anticipo. Il primo caricamento costa ~1,7 s per voce, e non
        deve capitare sulla prima battuta di una partita."""
        for n in names:
            self._voice(n)

    def _voice(self, name: str):
        cached = self._voices.get(name)
        if cached is not None:
            return cached
        try:
            from piper import PiperVoice
        except ImportError as e:  # pragma: no cover - dipende dall'ambiente
            raise RuntimeError(
                "piper-tts non installato: "
                "`.\\.venv\\Scripts\\python.exe -m pip install piper-tts`"
            ) from e
        voice = PiperVoice.load(str(model_path(name, self.download)))
        self._voices[name] = voice
        return voice

    def synthesize(self, text: str, voice: VoiceSpec, rate: float = 1.0) -> Speech:
        text = text.strip()
        if not text:
            return Speech(np.zeros(0, np.float32), self.samplerate, voice.voice_id, text=text)

        from piper import SynthesisConfig

        engine = self._voice(voice.base_voice)
        # Piper misura in "quanto e' lungo", noi in "quanto e' veloce": inversi.
        effective = max(0.1, rate * voice.rate)
        syn = SynthesisConfig(length_scale=1.0 / effective)

        chunks: list[np.ndarray] = []
        native_rate = self.samplerate
        t0 = time.perf_counter()
        first_ms = 0.0
        for chunk in engine.synthesize(text, syn_config=syn):
            if not chunks:
                first_ms = (time.perf_counter() - t0) * 1000.0
            chunks.append(
                np.frombuffer(chunk.audio_int16_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            )
            native_rate = chunk.sample_rate

        audio = np.concatenate(chunks) if chunks else np.zeros(0, np.float32)
        if audio.size and voice.semitones:
            audio = pitch_shift(audio, voice.semitones, samplerate=native_rate)
        if native_rate != self.samplerate:
            audio = resample(audio, native_rate, self.samplerate)
        total_ms = (time.perf_counter() - t0) * 1000.0

        self._native_rate[voice.base_voice] = native_rate
        return Speech(
            audio=audio,
            samplerate=self.samplerate,
            voice_id=voice.voice_id,
            first_sample_ms=first_ms,
            total_ms=total_ms,
            text=text,
        )
