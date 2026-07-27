"""Configurazione della pipeline.

Un solo albero di dataclass, con tutti i valori che si toccano durante il
tuning, e un modo per cambiarne uno solo dalla riga di comando:

    main.py --set vision.sat_max=70 --set tts.backend=tone

La ragione di `--set` invece di una raffica di flag e' che il tuning non si fa
con i valori previsti: si fa con quello che nessuno aveva previsto di dover
cambiare. Ogni campo qui dentro e' raggiungibile senza toccare l'argparse.

I default sono **punti di partenza dichiarati, non misure**. Le soglie di colore,
la ROI e i coefficienti di durata vanno ricavati dal video con
`tools/calibrate.py` e scritti nel profilo del gioco.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from pathlib import Path
from typing import Any


@dataclass
class CaptureConfig:
    """Cattura dello schermo."""

    backend: str = "auto"  # auto | wgc | dxcam | mss
    monitor: int = 1
    fps: float = 30.0  # ritmo del diff sulla ROI, non dell'OCR


@dataclass
class VisionConfig:
    """Lettura dei sottotitoli.

    `roi` e' normalizzata (x, y, w, h) sul frame, cosi' non dipende dalla
    risoluzione. Le tre soglie di colore implementano la grammatica: satura =>
    riga scartata, altrimenti bianco o grigio secondo la luminanza.
    """

    roi: tuple[float, float, float, float] = (0.15, 0.72, 0.70, 0.22)
    diff_threshold: float = 0.004  # frazione di pixel cambiati che sveglia l'OCR
    diff_stride: int = 4  # sottocampionamento del diff: costa 1/16 e basta
    sat_max: int = 60  # saturazione oltre la quale la riga non e' dialogo
    white_min_luma: int = 200  # bianco pieno
    grey_min_luma: int = 110  # sotto questa soglia non e' testo
    # Il testo di gioco e' bordato di nero: non e' luminoso in assoluto, e'
    # luminoso *rispetto a cio' che ha intorno*. Con la sola soglia assoluta un
    # cielo chiaro fa sparire i sottotitoli (misurato: si rompe da luma 120 in
    # su); togliendo un fondo locale il limite si sposta a 180.
    use_local_contrast: bool = True
    contrast_kernel: int = 63  # lato del fondo locale, in pixel
    contrast_min: float = 30.0  # quanto il glifo deve staccare dal suo intorno
    # Il corpo del glifo si misura su un percentile alto, non sulla mediana: il
    # testo e' antialiasato e bordato, e i pixel di bordo falserebbero la media.
    luma_percentile: int = 90
    sat_percentile: int = 98
    min_line_height: int = 8  # px: sotto e' rumore, non una riga
    min_line_fill: float = 0.01  # frazione minima di larghezza occupata da testo
    stable_reads: int = 2  # letture concordi prima di dare per buona una battuta
    hold_frames: int = 3  # frame senza testo prima di dichiarare chiusa la battuta
    ocr_backend: str = "ppocr"  # ppocr | none
    ocr_device: str = "cuda"  # cuda | cpu
    max_ocr_hz: float = 12.0


@dataclass
class AudioConfig:
    """Cattura dell'audio di gioco."""

    device: str = ""  # vuoto = device di loopback predefinito
    samplerate: int = 48000
    blocksize: int = 480  # 10 ms
    ring_seconds: float = 10.0
    center_enabled: bool = True  # estrazione mid/side per isolare il parlato


@dataclass
class VadConfig:
    backend: str = "silero"  # silero | energy
    threshold: float = 0.5
    min_speech_ms: int = 150
    min_silence_ms: int = 250


@dataclass
class SpeakerConfig:
    """Riconoscimento di chi parla.

    `use_color_cue` accende il vincolo che arriva dal video: due righe di
    luminanza diversa non possono finire nello stesso cluster.
    """

    backend: str = "ecapa-onnx"  # ecapa-onnx | mfcc | none
    similarity: float = 0.62  # soglia coseno per "e' la stessa voce"
    min_clip_ms: int = 400  # sotto questa durata la decisione e' provvisoria
    max_wait_ms: int = 200  # quanto si puo' rinviare l'attacco per decidere meglio
    max_speakers: int = 16
    use_color_cue: bool = True
    use_alternation: bool = True  # isteresi conversazionale


@dataclass
class EmotionConfig:
    """Tre segnali deboli fusi: modello audio, testo, livello dell'originale."""

    backend: str = "emotion2vec"  # emotion2vec | level | none
    w_audio: float = 0.5
    w_text: float = 0.2
    w_level: float = 0.3
    max_gain_db: float = 4.0
    max_rate_delta: float = 0.12
    max_semitones: float = 1.5


@dataclass
class TtsConfig:
    """Sintesi. `tone` e' un backend finto che produce un bip: serve al banco di
    prova per misurare la catena senza scaricare nulla."""

    backend: str = "piper"  # piper | qwen | tone
    voices: tuple[str, ...] = ("it_IT-paola-medium", "it_IT-riccardo-x_low")
    pool_size: int = 6  # voci distinte ottenute variando pitch e velocita'
    samplerate: int = 22050
    device: str = "cpu"


@dataclass
class TimingConfig:
    """Aggancio al parlato originale.

    `predict_a` e `predict_b` sono i coefficienti di `D = a + b * n_caratteri`.
    Valori iniziali plausibili, da rifare con `tools/calibrate.py`.
    """

    predict_a: float = 0.90
    predict_b: float = 0.045
    rate_min: float = 0.85
    rate_max: float = 1.35
    lead_ms: int = 0  # anticipo/ritardo fisso sull'attacco
    use_vad_onset: bool = True
    never_drop: bool = True  # oltre i limiti si sfora, non si scarta


@dataclass
class MixConfig:
    """Uscita audio. Il duck agisce sul solo canale centrale, dove sta il
    parlato: musica ed effetti restano intatti."""

    passthrough: bool = True
    duck_db: float = -14.0
    duck_attack_ms: int = 40
    duck_release_ms: int = 220
    dub_gain_db: float = 0.0
    output_device: str = ""


@dataclass
class UiConfig:
    enabled: bool = False
    log_dir: str = "runs"
    save_mix: bool = True


@dataclass
class Config:
    profile: str = "gtav"
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    vision: VisionConfig = field(default_factory=VisionConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    vad: VadConfig = field(default_factory=VadConfig)
    speaker: SpeakerConfig = field(default_factory=SpeakerConfig)
    emotion: EmotionConfig = field(default_factory=EmotionConfig)
    tts: TtsConfig = field(default_factory=TtsConfig)
    timing: TimingConfig = field(default_factory=TimingConfig)
    mix: MixConfig = field(default_factory=MixConfig)
    ui: UiConfig = field(default_factory=UiConfig)

    # -- override ----------------------------------------------------------

    def set(self, path: str, value: Any) -> Any:
        """Imposta `sezione.campo` convertendo al tipo del campo.

        Solleva `KeyError` se il percorso non esiste: un refuso in `--set` deve
        fermare l'avvio, non essere ignorato in silenzio.
        """
        parts = path.split(".")
        target: Any = self
        for part in parts[:-1]:
            if not is_dataclass(target) or not hasattr(target, part):
                raise KeyError(f"percorso di config sconosciuto: {path!r}")
            target = getattr(target, part)
        leaf = parts[-1]
        if not is_dataclass(target) or not hasattr(target, leaf):
            raise KeyError(f"percorso di config sconosciuto: {path!r}")
        current = getattr(target, leaf)
        coerced = _coerce(value, current, path)
        setattr(target, leaf, coerced)
        return coerced

    def get(self, path: str) -> Any:
        target: Any = self
        for part in path.split("."):
            if not hasattr(target, part):
                raise KeyError(f"percorso di config sconosciuto: {path!r}")
            target = getattr(target, part)
        return target

    def apply(self, overrides: list[str] | tuple[str, ...] | None) -> "Config":
        """Applica una lista di `chiave=valore`."""
        for item in overrides or ():
            if "=" not in item:
                raise ValueError(f"override malformato (serve chiave=valore): {item!r}")
            key, _, raw = item.partition("=")
            self.set(key.strip(), raw.strip())
        return self

    # -- serializzazione ---------------------------------------------------

    def to_dict(self) -> dict:
        return asdict(self)

    def dump(self) -> str:
        """Elenco piatto `sezione.campo = valore`, ordinato e diffabile.

        Il formato e' scelto per essere incollabile in un log di sessione: se
        una prova va male, la sua configurazione esatta e' una riga di testo.
        """
        out: list[str] = []

        def walk(prefix: str, obj: Any) -> None:
            for f in fields(obj):
                value = getattr(obj, f.name)
                name = f"{prefix}{f.name}"
                if is_dataclass(value):
                    walk(f"{name}.", value)
                else:
                    out.append(f"{name} = {_fmt(value)}")

        walk("", self)
        width = max((len(line.split(" = ")[0]) for line in out), default=0)
        return "\n".join(
            f"{line.split(' = ')[0].ljust(width)} = {line.split(' = ', 1)[1]}" for line in out
        )

    def save(self, path: str | Path) -> Path:
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return p

    @classmethod
    def load(cls, path: str | Path) -> "Config":
        """Carica un profilo. Le chiavi assenti restano ai default; una chiave
        sconosciuta e' un errore, non un refuso silenzioso."""
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        cfg = cls()
        for key, value in _flatten(data):
            cfg.set(key, value)
        return cfg


def _flatten(data: dict, prefix: str = "") -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    for key, value in data.items():
        name = f"{prefix}{key}"
        if isinstance(value, dict):
            out.extend(_flatten(value, f"{name}."))
        else:
            out.append((name, value))
    return out


def _coerce(value: Any, current: Any, path: str) -> Any:
    """Porta `value` al tipo di `current`. Il tipo corrente e' il contratto."""
    if isinstance(current, bool):
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in ("1", "true", "vero", "si", "on", "yes"):
            return True
        if text in ("0", "false", "falso", "no", "off"):
            return False
        raise ValueError(f"{path}: atteso un booleano, ricevuto {value!r}")
    if isinstance(current, int) and not isinstance(current, bool):
        return int(str(value).strip())
    if isinstance(current, float):
        return float(str(value).strip())
    if isinstance(current, tuple):
        items = value if isinstance(value, (list, tuple)) else str(value).split(",")
        proto = current[0] if current else 0.0
        return tuple(_coerce(x, proto, path) for x in items)
    if isinstance(current, str):
        return str(value)
    raise TypeError(f"{path}: tipo non gestito {type(current).__name__}")


def _fmt(value: Any) -> str:
    if isinstance(value, tuple):
        return ", ".join(_fmt(v) for v in value)
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, str) and value == "":
        return "(vuoto)"
    return str(value)
