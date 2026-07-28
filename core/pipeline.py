"""Il ponte fra i due domini.

Video e audio scorrono su ritmi diversi e non devono aspettarsi a vicenda: i
frame arrivano a 30 Hz e possono permettersi di far girare un OCR ogni tanto,
i blocchi audio arrivano ogni 10 ms e non possono permettersi niente. Il punto
di incontro e' uno solo, ed e' qui.

    on_frame(frame)  ->  legge i sottotitoli, sintetizza, PROGRAMMA
    on_audio(blocco) ->  versa quello che e' stato programmato, e mixa

La direzione e' sempre quella: il dominio video decide *cosa* si dira' e
*quando*, il dominio audio si limita a eseguire. Il mixer non chiama mai il
sintetizzatore, perche' sarebbe un'attesa dentro il percorso che non puo'
aspettare.

Stato F1: chi parla si deduce dalla sola classe cromatica del sottotitolo —
bianco e grigio ricevono due voci fisse. E' il segnaposto che F3 sostituisce con
l'embedding vero. Basta gia' a far sentire due personaggi diversi quando parlano
in contemporanea, che e' il caso in cui l'errore darebbe piu' fastidio.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from core.clock import Clock, get_clock
from core.config import Config
from core.metrics import MetricsRegistry
from core.types import Emotion, LineClass, SubtitleEvent, Utterance
from mix.mixer import Mixer
from speak.base import TtsBackend
from speak.pool import VoicePool, build_pool
from vision.ocr import OcrBackend, make_ocr
from vision.reader import SubtitleReader


@dataclass
class SpokenLine:
    """Una battuta effettivamente doppiata, con tutti i tempi per il log."""

    text: str
    speaker_id: str
    voice_id: str
    cls: str
    t_subtitle: float  # quando il sottotitolo e' comparso
    t_scheduled: float  # quando la voce italiana comincia
    synth_ms: float
    duration: float
    rate: float = 1.0

    @property
    def latency_ms(self) -> float:
        """Dalla comparsa del sottotitolo all'istante programmato per la voce.

        **Sul banco questo numero e' ottimista** e va letto insieme a
        `live_latency_ms`. Il replay usa un orologio virtuale, che avanza solo
        quando glielo si dice: mentre il sintetizzatore lavora davvero per
        novanta millisecondi, il tempo del media resta fermo. Dal vivo quei
        novanta millisecondi sono passati sul serio.
        """
        return (self.t_scheduled - self.t_subtitle) * 1000.0

    @property
    def live_latency_ms(self) -> float:
        """La latenza che si sentirebbe in gioco: programmazione piu' sintesi.

        Le due misure restano separate invece di essere sommate una volta per
        tutte perche' dicono cose diverse — la prima e' un ritardo di
        decisione, la seconda un costo di calcolo — e si riducono in modi
        diversi.
        """
        return self.latency_ms + self.synth_ms


class DubPipeline:
    """La catena completa, da frame e blocchi audio a uscita doppiata."""

    def __init__(
        self,
        cfg: Config,
        tts: TtsBackend,
        *,
        ocr: OcrBackend | None = None,
        clock: Clock | None = None,
        metrics: MetricsRegistry | None = None,
        samplerate: int = 48000,
    ) -> None:
        self.cfg = cfg
        self.tts = tts
        self.samplerate = samplerate
        self.metrics = metrics or MetricsRegistry()
        self._clock = clock

        self.reader = SubtitleReader(
            cfg.vision,
            ocr if ocr is not None else make_ocr(cfg.vision.ocr_backend, cfg.vision.ocr_device),
            metrics=self.metrics,
            clock=clock,
            on_error="bypass",  # in gioco una battuta persa e' meglio di una sessione persa
        )
        self.pool = VoicePool(build_pool(cfg.tts.voices, cfg.tts.pool_size))
        self.mixer = Mixer(
            samplerate=samplerate,
            duck_db=cfg.mix.duck_db,
            attack_ms=cfg.mix.duck_attack_ms,
            release_ms=cfg.mix.duck_release_ms,
            dub_gain_db=cfg.mix.dub_gain_db,
            passthrough=cfg.mix.passthrough,
            metrics=self.metrics,
        )

        self.spoken: list[SpokenLine] = []
        self.closed: list[SubtitleEvent] = []
        self._t_synth = self.metrics.timer("speak.synth")
        self._t_latency = self.metrics.timer("dub.latency")
        self._t_live = self.metrics.timer("dub.latency_live")
        self._n_lines = self.metrics.counter("dub.lines")
        self._n_empty = self.metrics.counter("dub.empty")

    @property
    def clock(self) -> Clock:
        return self._clock if self._clock is not None else get_clock()

    # -- avvio dal vivo ----------------------------------------------------

    def start_live(self, warmup: bool = True) -> None:
        """Da chiamare **quando l'audio comincia a scorrere**, non prima.

        Due difetti che si vedono solo dal vivo, e che questa riga chiude.

        **Gli orologi hanno due origini diverse.** L'orologio della sessione
        parte all'avvio del programma; quello del mixer avanza con l'audio
        processato, quindi parte quando il primo blocco arriva. In mezzo ci
        sono l'apertura dei device, il caricamento dei modelli e l'attesa per
        portare il gioco davanti: misurato, una ventina di secondi. Siccome
        `_speak` programma a `max(clock.now(), mixer.now)`, la prima battuta
        finiva venti secondi avanti nella linea temporale del mixer — e da li'
        in poi tutto arrivava con quel ritardo, **con le pause giuste**, che e'
        il sintomo con cui il difetto si e' fatto notare. Le pause erano giuste
        perche' i due orologi corrono alla stessa velocita': sbagliava solo
        l'origine. E' la stessa forma dell'errore dei due tempi in
        `core/stage.py`, in un travestimento nuovo.

        **Il primo `synthesize` carica il modello.** Misurato: fino a 1,9 s,
        contro i 60 ms di quelli dopo. Pagarlo sulla prima battuta vera
        significa perdere proprio quella, quindi lo si paga adesso su una frase
        che non deve andare in onda.
        """
        if warmup:
            try:
                self.tts.synthesize("via", self.pool.voices[0])
            except Exception:
                pass  # un riscaldamento fallito non e' un motivo per non partire
        self.mixer.reset(self.clock.now())

    # -- dominio video -----------------------------------------------------

    def on_frame(self, frame: np.ndarray | None) -> list[SpokenLine]:
        """Un frame in ingresso. Restituisce le battute doppiate in questa passata."""
        out = self.reader.run(frame)
        self.closed.extend(out.closed)
        return [self._speak(ev) for ev in out.opened if ev.text.strip()]

    def _speak(self, event: SubtitleEvent) -> SpokenLine:
        """Da battuta letta a audio programmato."""
        speaker_id = self._speaker_for(event)
        voice = self.pool.voice_for(speaker_id, event.t_on)

        t0 = time.perf_counter()
        speech = self.tts.synthesize(event.text, voice)
        synth_ms = (time.perf_counter() - t0) * 1000.0
        self._t_synth.add(synth_ms)

        audio = speech.audio
        if speech.samplerate != self.samplerate and audio.size:
            from mix.stretch import resample

            audio = resample(audio, speech.samplerate, self.samplerate)

        now = self.clock.now()
        t_start = max(now, self.mixer.now)
        if audio.size:
            self.mixer.schedule(
                audio, t_start, speaker_id=speaker_id, text=event.text
            )
            self._n_lines.inc()
        else:
            self._n_empty.inc()

        line = SpokenLine(
            text=event.text,
            speaker_id=speaker_id,
            voice_id=voice.voice_id,
            cls=event.cls.value,
            t_subtitle=event.t_on,
            t_scheduled=t_start,
            synth_ms=synth_ms,
            duration=len(audio) / self.samplerate if audio.size else 0.0,
        )
        self._t_latency.add(line.latency_ms)
        self._t_live.add(line.live_latency_ms)
        self.spoken.append(line)
        return line

    def _speaker_for(self, event: SubtitleEvent) -> str:
        """Chi parla.

        F1: la sola classe cromatica. Il bianco e' lo speaker principale, il
        grigio quello che gli si sovrappone. Non dice *quale* personaggio sia —
        per quello serve l'embedding di F3 — ma dice con certezza che sono due
        persone diverse, che e' l'informazione piu' urgente.
        """
        return "S-grey" if event.cls is LineClass.GREY else "S-white"

    # -- dominio audio -----------------------------------------------------

    def on_audio(self, game: np.ndarray | None, n: int | None = None) -> np.ndarray:
        """Un blocco di audio di gioco. Restituisce il blocco da mandare in uscita."""
        return self.mixer.process(game, n)

    # -- chiusura ----------------------------------------------------------

    def finish(self) -> None:
        """Chiude le battute ancora a schermo: senza, l'ultima resta senza durata."""
        self.closed.extend(self.reader.close().closed)

    def report(self) -> str:
        righe = [
            f"battute doppiate: {len(self.spoken)}",
            f"personaggi sentiti: {len(self.pool)}",
            "",
            self.pool.report(),
            "",
            self.metrics.report(),
        ]
        return "\n".join(righe)
