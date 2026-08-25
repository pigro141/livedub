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

**E le voci non sono due: sono 175, in cinquanta lingue.** Il catalogo sta in
`piper_voci.py`; qui c'e' solo il download, che passa dalla stessa strada di
sempre. Fino a ieri questo file ne conosceva due, e chi traduceva in spagnolo
sentiva una voce italiana leggere lo spagnolo — senza nessun errore.
"""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np

from core.types import VoiceSpec
from mix.stretch import pitch_shift, resample
from speak.base import Speech, taglia_silenzio

# Dove stanno i modelli e come si chiamano dentro il repo di Rhasspy.
MODELS_DIR = Path(__file__).resolve().parents[2] / "models" / "piper"
REPO = "rhasspy/piper-voices"

# Il catalogo ufficiale, scritto nel repo, con la regola che ricava il percorso
# dalla chiave. Cinquantuno lingue nell'indice, cinquanta dicibili: si veda
# `SPECIALI` per l'unica che cade e per il motivo.
from speak.backends.piper_voci import (  # noqa: E402
    LINGUE, MULTI, VOCI, normale, parlante, sottopercorso, voci_per,
)

# Lettere e cifre al secondo alla velocita' nominale, **nell'unita' di
# `spoken_length()`** — che e' quella di chi lo usa: contando anche spazi e
# punteggiatura la stessa passata darebbe 18,3, ed e' da quella confusione che
# veniva il 17,4 rimasto sbagliato in config per anni.
#
# L'italiano e' misurato su dodici battute vere della registrazione con
# `riccardo`: 320 caratteri in 21,6 s **una volta tolto il silenzio in coda**,
# che erano 3,1 secondi su 23,6. Le altre lingue si misurano con
# `tools/censisci_voci.py --misura`, stesso metodo: `spoken_length(testo) /
# durata` dopo `taglia_silenzio`.
#
# **Chi aggiunge una lingua misuri la sua.** Un numero preso da un'altra lingua
# e' esattamente il difetto che questa tabella esiste per chiudere: con i 12,9
# dell'italiano applicati all'inglese, Kokoro comprimeva ogni battuta al tetto
# in una scena piena al 49%.
PASSO_PER_DEFAULT = 14.8
PASSO_LINGUA: dict[str, float] = {
    "it": 14.8,
    # **Una sola, e c'e' un motivo che vale la pena scrivere.** Su questa
    # macchina Smart App Control blocca `espeakbridge.pyd`, e tutte le altre
    # cinquanta lingue di Piper passano da espeak: non sono misurabili qui. L'
    # ebraico e' l'unica che non ci passa (`phoneme_type: hebrew`), quindi e'
    # l'unica che si e' potuta cronometrare — una frase, 9,14 car/s.
    "he": 9.1,
}


def model_path(name: str, download: bool = True) -> Path:
    """Percorso del modello, scaricandolo alla prima richiesta.

    Il download avviene una volta sola e finisce in `models/`, che e'
    gitignorato: sono 28-114 MB per voce, materiale della macchina.

    `name` puo' portare un `#indice` — il parlante dentro un modello multiplo —
    che qui non conta: il file e' lo stesso per tutti i suoi parlanti, ed e'
    l'unica ragione per cui quei modelli valgono la pena.
    """
    chiave = name.split("#")[0]
    lingua = chiave.split("_")[0]
    if chiave not in VOCI.get(lingua, ()):
        raise ValueError(
            f"voce Piper sconosciuta: {name!r} "
            f"(il catalogo ne ha {sum(len(v) for v in VOCI.values())} in {len(LINGUE)} lingue)"
        )
    parlante(name)  # un `speaker_id` fuori scala non da' errore: da' un'altra voce
    sub = sottopercorso(chiave)
    local = MODELS_DIR / sub / f"{chiave}.onnx"
    if local.exists() and local.with_suffix(".onnx.json").exists():
        return local
    if not download:
        raise FileNotFoundError(f"modello non presente: {local}")

    from huggingface_hub import hf_hub_download

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    hf_hub_download(REPO, f"{sub}/{chiave}.onnx", local_dir=MODELS_DIR)
    hf_hub_download(REPO, f"{sub}/{chiave}.onnx.json", local_dir=MODELS_DIR)
    return local


class PiperTts:
    """Sintesi Piper con pool di voci caricate su richiesta."""

    name = "piper"

    def __init__(self, samplerate: int = 22050, download: bool = True,
                 lingua: str = "it") -> None:
        self.samplerate = samplerate
        self.download = download
        # La lingua **del testo che verra' detto**: serve solo al passo, perche'
        # a Piper la lingua la dichiara il modello e non un parametro.
        self.lingua_base = normale(lingua)
        self._voices: dict[str, object] = {}
        self._native_rate: dict[str, int] = {}

    @property
    def chars_per_second(self) -> float:
        """Lettere e cifre al secondo, nell'unita' di `spoken_length()`.

        **Per lingua**, e non e' pignoleria: e' la quarta volta in questo
        progetto che un passo misurato su una lingua viene applicato a un'altra,
        e l'ultima ha fatto uscire `dub.rate_x1000` inchiodato al tetto su ogni
        percentile con la scena piena a meta'. Le lingue non misurate ricadono
        sull'italiano, che e' il numero misurato bene — si veda `PASSO_LINGUA`.
        """
        return PASSO_LINGUA.get(self.lingua_base, PASSO_PER_DEFAULT)

    def preload(self, names: list[str]) -> None:
        """Carica in anticipo. Il primo caricamento costa ~1,7 s per voce, e non
        deve capitare sulla prima battuta di una partita."""
        for n in names:
            self._voice(n)

    def _voice(self, name: str):
        # **La cache e' sul modello, non sulla voce.** I parlanti di un modello
        # multiplo condividono lo stesso file: caricarlo una volta per parlante
        # vorrebbe dire pagare 904 volte lo stesso 1,7 s.
        name = name.split("#")[0]
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
        syn = SynthesisConfig(
            length_scale=1.0 / effective,
            # Il parlante dentro un modello multiplo. Zero per i modelli a una
            # voce, dove Piper lo ignora.
            speaker_id=parlante(voice.base_voice) or None,
        )

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
        # Anche Piper imbottisce, molto meno — 3,1 secondi su 23,6, quasi tutti
        # in coda — ma e' silenzio che poi la catena comprime come se fosse
        # parlato. Si toglie qui per la stessa ragione: lo stacco fra le battute
        # lo mette `tts.gap_seconds`, che sa anche togliersi di mezzo quando si
        # e' in ritardo.
        audio = taglia_silenzio(audio, native_rate)
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
