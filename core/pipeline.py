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
from fuse.timing import DurationModel, spoken_length
from mix.mixer import Mixer
from mix.stretch import fit_duration, fit_duration_keep_tail  # noqa: F401
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
        # Il pool segue il backend: senza, una sessione SuperTonic riceverebbe
        # in dote le voci di Piper e non saprebbe pronunciarle.
        self.pool = VoicePool(
            build_pool(cfg.tts.voices, cfg.tts.pool_size, backend=cfg.tts.backend)
        )
        self.mixer = Mixer(
            samplerate=samplerate,
            duck_db=cfg.mix.duck_db,
            attack_ms=cfg.mix.duck_attack_ms,
            release_ms=cfg.mix.duck_release_ms,
            dub_gain_db=cfg.mix.dub_gain_db,
            passthrough=cfg.mix.passthrough,
            hold_ms=cfg.mix.duck_hold_ms,
            metrics=self.metrics,
        )

        self.spoken: list[SpokenLine] = []
        self.closed: list[SubtitleEvent] = []
        self._free_at = 0.0  # quando la voce torna libera
        self.timing = DurationModel(cfg.timing)
        # **Quanto in fretta parla questa voce quando non le si chiede niente.**
        # Il valore di config e' un punto di partenza dichiarato; quello vero si
        # misura sulle battute che non hanno avuto bisogno di fretta, che sono la
        # maggioranza. Serve da riferimento sia al tetto sia alla metrica: senza,
        # "compressione 1,2" vorrebbe dire "un quinto piu' veloce di quanto
        # credevo io", che non e' una proprieta' della battuta ma della mia
        # assunzione.
        self._cps = float(cfg.tts.chars_per_second)
        self._cps_n = 0
        self._t_backlog = self.metrics.timer("dub.backlog")
        self._t_rate = self.metrics.timer("dub.rate_x1000")
        self._t_hurry = self.metrics.timer("dub.hurry_x1000")
        self._t_nativo = self.metrics.timer("dub.native_x1000")
        self._n_collision = self.metrics.counter("dub.collision")
        self._n_overflow = self.metrics.counter("dub.overflow")
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
            # **Tutte le voci del pool, non la prima.** Scaldarne una sola
            # manteneva la promessa per il primo personaggio e la rompeva per il
            # secondo: misurato dal vivo in due sessioni diverse, la prima
            # battuta di `paola` e' costata 1826 ms e 1800 ms di sintesi contro
            # un p50 di 52 ms — cioe' esattamente il difetto che questa riga
            # esiste per evitare, spostato di un personaggio piu' in la'. E
            # capita nel momento peggiore: la seconda voce entra quando due
            # personaggi si parlano sopra, che e' quando una battuta persa si
            # nota di piu'.
            for voce in self.pool.voices:
                try:
                    self.tts.synthesize("via", voce)
                except Exception:
                    pass  # un riscaldamento fallito non e' un motivo per non partire
        self.mixer.reset(self.clock.now())
        self._free_at = self.clock.now()

    # -- dominio video -----------------------------------------------------

    def on_frame(self, frame: np.ndarray | None) -> list[SpokenLine]:
        """Un frame in ingresso. Restituisce le battute doppiate in questa passata."""
        out = self.reader.run(frame)
        self.closed.extend(out.closed)
        # Una battuta che sparisce e' una durata vera: il predittore impara da
        # quelle, e sono l'unica forma in cui la calibrazione del tempo si
        # aggiorna mentre la sessione gira.
        for ev in out.closed:
            if ev.duration is not None:
                self.timing.observe(ev.text, ev.duration)
        return [self._speak(ev) for ev in out.opened if ev.text.strip()]

    def _speak(self, event: SubtitleEvent) -> SpokenLine:
        """Da battuta letta a audio programmato."""
        speaker_id = self._speaker_for(event)
        voice = self.pool.voice_for(speaker_id, event.t_on)

        # **Chiedere al sintetizzatore di parlare svelto, invece di schiacciarlo
        # dopo.** Sono due cose diverse e all'ascolto non si somigliano affatto:
        # WSOLA ripete e butta via pezzi di forma d'onda, e sopra 1,3 le
        # consonanti spariscono — la voce "si mangia le parole". Un TTS a cui si
        # chiede di andare piu' in fretta articola comunque tutto, come un
        # attore che parla svelto invece di un nastro mandato avanti.
        #
        # La velocita' va decisa **prima** di sintetizzare, quindi la durata si
        # stima dal testo e non si misura: `chars_per_second` e' quella misurata
        # per il backend. Sbagliarla non rovina la battuta, lascia solo un
        # residuo piu' grosso a WSOLA — che e' esattamente il lavoro che WSOLA
        # sa fare bene, perche' sulla durata e' esatto mentre `length_scale` non
        # e' nemmeno proporzionale.
        nativo = 1.0
        n = spoken_length(event.text)
        if self.cfg.tts.native_rate_max > 1.0:
            stima = n / max(1e-6, self._cps)
            budget = self.timing.plan(
                event.text, stima, elapsed=max(0.0, self.clock.now() - event.t_on)
            ).budget
            if budget <= 0.05:
                # Finestra gia' finita: si e' comunque in ritardo, e allora tanto
                # vale che a parlare svelto sia il sintetizzatore invece di
                # WSOLA. E' il caso in cui la differenza fra le due si sente di
                # piu', perche' e' quello in cui si accelera di piu'.
                nativo = self.cfg.tts.native_rate_max
            elif stima > budget:
                nativo = min(self.cfg.tts.native_rate_max, stima / budget)

        t0 = time.perf_counter()
        speech = self.tts.synthesize(event.text, voice, rate=nativo)
        synth_ms = (time.perf_counter() - t0) * 1000.0
        if nativo > 1.0:
            self._t_nativo.add(nativo * 1000.0)
        self._t_synth.add(synth_ms)

        audio = speech.audio
        if speech.samplerate != self.samplerate and audio.size:
            from mix.stretch import resample

            audio = resample(audio, speech.samplerate, self.samplerate)

        # La velocita' naturale della voce si impara dalle battute a cui non e'
        # stata chiesta fretta: li' la durata che torna **e'** quella naturale,
        # e non c'e' niente da dedurre. Il peso cala col numero di campioni,
        # cosi' i primi contano molto e poi il valore si assesta.
        if nativo <= 1.0 and audio.size and n >= 8:
            misurato = n / (len(audio) / self.samplerate)
            self._cps_n += 1
            self._cps += min(0.25, 1.0 / self._cps_n) * (misurato - self._cps)

        now = self.clock.now()
        # **La battuta nuova e' arrivata: quella in corso ha finito il suo tempo.**
        # Sul banco, una battuta su tre invaderebbe la successiva, ed e' l'unico
        # sforamento che fa danno — due voci accavallate fanno perdere una riga,
        # mentre una voce che continua a schermo vuoto non disturba nessuno.
        #
        # Qui non si prevede niente: `D = a + b*n` ha R2 0,15 sulla registrazione
        # vera, cioe' la lunghezza spiega il quindici per cento della durata e
        # nessuna previsione salva. L'arrivo di *questo* sottotitolo invece non e'
        # una stima, e' un fatto, e capita nell'istante esatto in cui la
        # decisione va presa. Si stringe il residuo non ancora suonato di cio'
        # che sta parlando, e cio' che e' gia' uscito resta com'era.
        #
        # La condizione e' "sta **suonando** qualcosa", non "la voce e'
        # occupata": `_free_at` comprende i 120 ms di respiro fra una battuta e
        # l'altra, quindi e' nel futuro anche quando l'audio e' gia' finito. Il
        # contatore, con la prima versione, dichiarava una collisione dove non
        # ce n'era — e un contatore che conta piu' di cio' che nomina fa perdere
        # tempo la prima volta che qualcuno lo legge.
        if self.cfg.timing.hurry_on_next and self.mixer.speaking:
            self._n_collision.inc()
            fretta = self.mixer.hurry(
                now,
                limits=(1.0, self.cfg.timing.rate_max),
                min_residue=self.cfg.timing.hurry_min_residue_ms / 1000.0,
            )
            if fretta > 1.0:
                # La coda si e' accorciata di quanto lo stiramento ha guadagnato.
                self._free_at = self.mixer.finisce_a + self.cfg.tts.gap_seconds
                self._t_hurry.add(fretta * 1000.0)

        # **Una voce alla volta.** Il mixer somma tutto cio' che e' attivo, e
        # senza questa riga due sottotitoli vicini partivano insieme: due voci
        # italiane sovrapposte non si capiscono, ed e' peggio di una battuta in
        # ritardo. Ogni battuta comincia quindi quando finisce la precedente.
        t_start = max(now, self.mixer.now, self._free_at)
        self._t_backlog.add((t_start - now) * 1000.0)

        # **E la si stringe perche' ci stia, invece di spostarla in avanti.**
        # Mettere le battute in fila, da solo, sposta il problema: misurato dal
        # vivo, l'arretrato arrivava a 2 s con Piper e a 3 s con SuperTonic, e
        # non si smaltiva piu' perche' ogni battuta nuova nasceva gia' in coda.
        # Il rimedio e' il tempo, non lo spazio: la battuta ha una finestra —
        # quella del suo sottotitolo, prevista da `D = a + b*n` — e dentro
        # quella deve entrare.
        #
        # `elapsed` e' il tempo gia' consumato dalla comparsa del sottotitolo
        # fino a quando la voce potra' partire: comprende il riconoscimento, la
        # sintesi e l'attesa in coda. E' quello che riduce il budget, e non
        # tenerne conto significherebbe comprimere per una finestra che non
        # c'e' piu'.
        #
        # Si accelera soltanto. Rallentare per riempire il tempo disponibile
        # farebbe parlare il doppiatore piu' lento del personaggio senza nessun
        # guadagno, e `rate_min` esiste solo come limite inferiore di sicurezza
        # quando la correzione viene chiesta da qualcun altro.
        rate = 1.0
        if audio.size:
            durata = len(audio) / self.samplerate
            piano = self.timing.plan(event.text, durata, elapsed=t_start - event.t_on)
            # Il bersaglio, non la velocita': quando il budget e' gia' finito
            # `plan` restituisce `rate` 1.0 — non perche' vada bene cosi', ma
            # perche' non c'e' piu' finestra da rispettare. Guardare `rate`
            # spegneva la compressione **proprio quando serviva di piu'**, ed e'
            # il primo caso che la verifica ha trovato. Il pavimento
            # `durata / rate_max` dice: se non c'e' piu' spazio, stringi quanto
            # e' lecito e poi sfora.
            #
            # **I due fattori si riportano separati, e non si moltiplicano.**
            # Quanto Piper abbia davvero accelerato non e' misurabile senza
            # sintetizzare due volte la stessa battuta — `length_scale` non e'
            # proporzionale, chiedendo 1,30 ne arriva meno — quindi qualunque
            # "totale" stampato qui sarebbe una stima travestita da misura.
            #
            # Un primo tentativo lo stimava dal conteggio dei caratteri
            # (`naturale/finale`) e la verifica l'ha bocciato subito: quel
            # rapporto misura quanto e' veloce il *backend* rispetto ai
            # caratteri al secondo che gli avevo attribuito, e su una voce piu'
            # lenta dava 0,85 senza che si fosse compresso niente. Una metrica
            # sbagliata qui e' peggio di nessuna metrica, perche' e' su questa
            # che si decide se la voce sta correndo troppo.
            #
            # Quindi: `dub.rate_x1000` resta **il fattore WSOLA**, esatto e
            # confrontabile con tutte le sessioni di prima, e la fretta chiesta
            # al sintetizzatore sta in `dub.native_x1000`, dichiarata per quello
            # che e' — una richiesta.
            bersaglio = max(piano.budget, durata / self.cfg.timing.rate_max)
            if durata > bersaglio + 1e-3:
                # La coda non passa da WSOLA: lo stiramento perde la fine di
                # cio' che comprime, e la fine e' l'ultima parola.
                audio, rate = fit_duration_keep_tail(
                    audio,
                    bersaglio,
                    self.samplerate,
                    limits=(1.0, self.cfg.timing.rate_max),
                    tail_seconds=self.cfg.timing.keep_tail_seconds,
                )
            self._t_rate.add(rate * 1000.0)
            if piano.overflow > 0:
                # Oltre il limite si sfora, non si scarta: e' la promessa del
                # prodotto. Ma lo sforamento si conta, perche' e' il sintomo che
                # dice se la previsione di durata regge.
                self._n_overflow.inc()

        if audio.size:
            self.mixer.schedule(
                audio, t_start, speaker_id=speaker_id, text=event.text, rate=rate
            )
            self._free_at = t_start + len(audio) / self.samplerate + self.cfg.tts.gap_seconds
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
            rate=rate,
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
