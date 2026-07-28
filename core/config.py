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
    # Quanto testo deve vedere il diff per dire "c'e' un sottotitolo", misurato
    # in **pixel di testo per colonna** della ROI sottocampionata. Per colonna e
    # non per area: una frazione dell'area dipende da quanto e' alta la ROI, e
    # lo stesso identico sottotitolo dentro una ROI quattro volte piu' alta
    # darebbe un quarto del valore. Per colonna il numero e' lo stesso.
    #
    # Misurato: una riga di sottotitolo sintetico 0,54; su 2000 frame di gioco
    # con sottotitolo il minimo e' 0,243; a schermo vuoto la mediana e' 0,18.
    # La soglia va **sotto** il minimo osservato, perche' un falso "non c'e'
    # testo" chiude una battuta ancora a schermo e la fa riaprire, mentre un
    # falso "c'e' testo" ritarda solo la chiusura di `hold_frames`.
    ink_min_columns: float = 0.20
    sat_max: int = 60  # saturazione oltre la quale un pixel non e' un glifo di dialogo
    # Quanta parte dell'inchiostro di una riga puo' essere satura prima che la
    # riga smetta di essere dialogo.
    #
    # La prima versione bocciava la riga sul **picco** di saturazione, e
    # sbagliava per una ragione che si e' vista solo sulla registrazione: i
    # pixel saturi spesso non sono glifi, sono scenario entrato nella ROI. Una
    # battuta bianca a luminanza 253 veniva scartata perche' una macchia viola
    # passava nell'inquadratura — 863 righe scartate in venti minuti, e leggendo
    # cosa contenevano erano quasi tutte dialogo.
    #
    # Ordinando le righe scartate per quota di inchiostro saturo, le due
    # popolazioni si separano: sopra ~0,25 ci sono le righe-obiettivo (`Scegli
    # una delle auto`, `Raggiungi ...`, `Segui ...`, dove la parola colorata e'
    # una frazione grossa di una riga corta), sotto c'e' il dialogo con lo
    # scenario dentro la ROI. I pixel saturi vengono comunque tolti dalla
    # maschera prima del riconoscimento: non sono testo, e nel ritaglio danno
    # solo fastidio.
    sat_ink_max: float = 0.25
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
    # Quanto la banda di una riga puo' crescere oltre il proprio nucleo, in
    # frazione dell'altezza del nucleo. Serve a non tagliare code e punti: le
    # righe-pixel dove passano solo le code di g, q, p hanno pochi pixel e non
    # superano `min_line_fill`. Vedi `vision/lines.find_bands`.
    line_grow: float = 0.45
    # Ultimo filtro, e l'unico che non viene da una misura ma dalla lingua:
    # nessuna battuta italiana e' lunga una lettera. Sulla registrazione vera
    # la texture della scena produce righe che l'OCR legge come '1', '?', '—';
    # passavano ogni soglia di colore perche' un cordolo bianco *e'* bianco.
    # Si contano **lettere e cifre**: una riga letta '·..··' ha cinque caratteri
    # e nessuna lettera, e non e' una battuta in nessuna lingua.
    min_ocr_chars: int = 2
    stable_reads: int = 2  # letture concordi prima di dare per buona una battuta
    # Quanto una battuta puo' non farsi leggere restando a schermo: **entrambe**
    # le condizioni devono cadere prima di dichiararla chiusa.
    #
    # `hold_frames` conta le passate del tracker, e non e' un ripiego: una
    # passata avviene quando la scena cambia, e un sottotitolo che sparisce *e'*
    # un cambiamento — sostituire il conteggio col solo tempo e' stato provato e
    # peggiora (1105 aperture contro 1129 del migliore tempo puro).
    # `hold_seconds` mette il pavimento che al conteggio manca nelle scene
    # mosse, dove tre passate valgono un decimo di secondo. 0,6 s copre il
    # novantesimo percentile delle raffiche di letture fallite misurate sui 27
    # minuti (17 passate).
    #
    # Puo' essere generoso perche' la sparizione vera arriva dal diff
    # (`certain`), non dal silenzio dell'OCR: sbagliare per eccesso allunga una
    # durata, sbagliare per difetto spezza la battuta in due.
    #
    # **Da solo non serviva a niente**: finche' la sostituzione scavalcava la
    # scadenza (64% delle chiusure passava di li') allungare la tenuta non
    # cambiava una virgola. Ha cominciato a pagare solo insieme a
    # `continue_similarity`, ed e' il motivo per cui i due valori vanno tarati
    # insieme e non uno per volta.
    hold_frames: int = 3
    hold_seconds: float = 0.6
    # Quanto due letture possono differire restando "la stessa battuta". Si
    # confrontano le forme normalizzate (sole lettere e cifre), e il conto e' in
    # **caratteri**, non in percentuale: l'OCR sbaglia una lettera ogni tanto,
    # non una quota del testo. Vedi `vision/subtitles.wrong_chars`.
    # Misurato sulla fetta di 50 s: 2 caratteri danno 33 aperture, 3 ne danno
    # 30, 4 ne danno 29, 5 ne danno 28. Il salto e' fra 2 e 3 e poi la curva si
    # appiattisce, quindi 3 prende quasi tutto il guadagno restando vicino al
    # CER misurato dell'OCR (2,9%) — cioe' senza essere tarato sulla fetta.
    max_wrong_chars: int = 3  # sempre tollerati, a qualunque lunghezza
    max_wrong_frac: float = 0.06  # e in piu' questa quota della battuta piu' lunga
    # Soglia separata e piu' larga per un caso solo: una battuta appena
    # confermata che sta per cacciare l'**unica** orfana a schermo. Li' le
    # candidate sono due e la domanda e' piu' facile che nel caso generale,
    # quindi ci si puo' permettere di essere generosi senza rischiare di fondere
    # due frasi diverse in mezzo a molte. Vedi `SubtitleTracker.feed`.
    #
    # Il valore viene da una guardia della suite, non da una spazzata: a 0,60 il
    # banco dava il risultato migliore (692 aperture contro 742), ma `prima
    # battuta` e `seconda battuta` si somigliano per 0,62 e venivano fuse. Due
    # righe che finiscono con la stessa parola sono un caso reale, quindi la
    # soglia sta sopra quella fascia e si tiene l'83% del guadagno.
    continue_similarity: float = 0.75
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
    """Quando qualcuno comincia a parlare nell'audio del gioco."""

    backend: str = "energy"  # energy | silero (silero non ancora implementato)
    threshold: float = 0.5  # probabilita', per i backend a modello
    min_speech_ms: int = 150
    min_silence_ms: int = 250
    frame_ms: int = 20  # risoluzione della decisione, e quindi dell'onset
    # Il parlato non si riconosce da quanto e' forte ma da quanto **stacca** dal
    # rumore di fondo: l'audio di un gioco passa da una stanza silenziosa a un
    # inseguimento in tre secondi, e una soglia assoluta direbbe "parla sempre"
    # nel secondo caso e "non parla mai" nel primo. Stessa forma del contrasto
    # locale che trova i glifi.
    energy_margin_db: float = 9.0
    floor_window_ms: int = 3000  # su quanto passato si stima il fondo
    floor_percentile: int = 25
    floor_db: float = -55.0  # sotto questo livello e' silenzio comunque


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

    backend: str = "piper"  # piper | supertonic | tone
    # Vuoto = le native del backend scelto. Dichiararle serve solo a
    # restringere: la lista di Piper non ha senso per SuperTonic e viceversa.
    voices: tuple[str, ...] = ()
    pool_size: int = 6  # voci distinte ottenute variando pitch e velocita'
    samplerate: int = 22050
    device: str = "cpu"
    # Respiro fra una battuta e la successiva. Non e' estetica: due battute
    # attaccate senza stacco si sentono come una frase sola, e in un dialogo
    # fanno sembrare che parli sempre la stessa persona.
    gap_seconds: float = 0.12
    # Solo per SuperTonic. `steps` sono i passi di diffusione: quattro bastano,
    # otto costano il doppio. `speed` non e' un gusto ma una misura — a 1,50 il
    # ritmo pareggia quello di Piper (17,1 caratteri al secondo contro 17,4),
    # che all'ascolto era gia' giusto. A 1,05, il default del pacchetto, la
    # stessa frase durava il 47% in piu'.
    steps: int = 4
    speed: float = 1.50


@dataclass
class TimingConfig:
    """Aggancio al parlato originale.

    `predict_a` e `predict_b` sono i coefficienti di `D = a + b * n_caratteri`,
    e si misurano con `tools/bench_timing.py --write profiles/<gioco>.json`.
    I valori qui sotto sono **dichiarati, non misurati**: servono solo a far
    partire una sessione su un gioco mai calibrato.
    """

    predict_a: float = 0.90
    predict_b: float = 0.045
    # Fascia di plausibilita' di una durata: fuori di qui non e' una battuta.
    # Sotto, e' il frammento di una battuta riaperta a meta'; sopra, e' un
    # sottotitolo rimasto a schermo perche' il gioco e' in pausa o in un filmato.
    # Serve alla previsione (che non deve restituire assurdita') e
    # all'apprendimento (che non deve impararle).
    min_duration: float = 0.6
    max_duration: float = 8.0
    rate_min: float = 0.85
    rate_max: float = 1.35
    lead_ms: int = 0  # anticipo/ritardo fisso sull'attacco
    use_vad_onset: bool = True
    never_drop: bool = True  # oltre i limiti si sfora, non si scarta
    # Aggiornamento in linea dei coefficienti: `decay` e' quanto pesa il
    # passato a ogni nuova battuta (0,97 ≈ una memoria di una trentina), e
    # `max_drift` quanto la retta imparata puo' allontanarsi da quella del
    # profilo — la guardia contro l'imparare bene una cosa sbagliata.
    learn_decay: float = 0.97
    learn_min_samples: int = 12
    learn_max_drift: float = 0.35


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
        sconosciuta e' un errore, non un refuso silenzioso.

        Le chiavi che cominciano per `_` sono l'eccezione: sono commenti e
        metadati, non configurazione. `tools/calibrate.py` ci scrive dentro la
        misura che ha prodotto i valori — quale video, quanti frame, che
        istogrammi — perche' un numero senza la sua misura e' di nuovo un
        numero indovinato, solo con piu' cifre decimali.
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        cfg = cls()
        for key, value in _flatten(data):
            if key.split(".")[0].startswith("_"):
                continue
            cfg.set(key, value)
        return cfg


PROFILES_DIR = Path(__file__).resolve().parent.parent / "profiles"


def load_profile(name: str = "gtav", overrides: Any = None) -> Config:
    """Profilo del gioco come base, `--set` sopra.

    L'ordine conta: il profilo porta i valori **calibrati sul gioco**, `--set`
    serve a scostarsene per una prova singola senza sporcare il profilo. Sta
    qui e non in `main.py` perche' il banco di prova deve poter caricare
    esattamente la stessa configurazione del live: una misura fatta con soglie
    diverse da quelle che gireranno in gioco non misura il gioco.
    """
    path = PROFILES_DIR / f"{name}.json"
    cfg = Config.load(path) if path.exists() else Config()
    cfg.profile = name
    cfg.apply(overrides)
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
