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

import json
import re
import sys
import threading
import time
import unicodedata
from dataclasses import dataclass, field, replace
from difflib import SequenceMatcher

import numpy as np

from core.clock import Clock, VirtualClock, get_clock
from core.config import Config
from core.metrics import MetricsRegistry
from core.types import Emotion, LineClass, SubtitleEvent, Utterance
from core.ring import Overrun, RingBuffer
from fuse.timing import DurationModel, spoken_length
from listen.speaker import Decisione, SpeakerTracker, stima_f0
from listen.vad import make_vad
from mix.center import split
from mix.mixer import Mixer
from mix.stretch import fit_duration, fit_duration_keep_tail  # noqa: F401
from speak.base import TtsBackend, sa_streaming
from speak.pool import VoicePool, build_pool, voce_neutra, voce_per
from vision.label import LabelReader
from vision.ocr import OcrBackend, make_ocr
from vision.reader import SubtitleReader
from vision.subtitles import contenimento


def _lettere(testo: str) -> str:
    """Solo lettere e cifre, minuscole, accenti sciolti.

    Fra due letture della stessa battuta cio' che cambia di piu' e' la
    punteggiatura che l'OCR inventa sui bordi dei glifi: `'Via! Via!'` e
    `'Via, Via.'` sono la stessa frase, e un confronto letterale direbbe di no.
    Stessa normalizzazione di `NormalizeTextForHash` in RSTGameTranslation.
    """
    piatto = unicodedata.normalize("NFKD", testo.lower())
    return re.sub(r"[^a-z0-9]", "", piatto)


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
        # La voce di chi non si sa ancora chi sia. Fuori dal pool: nessuno se la
        # tiene, quindi non diventa mai la voce di un personaggio.
        self._neutra = voce_neutra(self.pool.voices, backend=cfg.tts.backend)
        # Chi parla scritto dal gioco, se il gioco lo scrive. Spento di default:
        # si veda `LabelConfig`, dove sta anche il perche' non si indovina.
        self.label = LabelReader(cfg.label) if cfg.label.enabled else None
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

        # **Chi parla.** L'analisi dell'audio serve a due momenti diversi e
        # lontani fra loro: quando bisogna parlare (poco parlato, si sceglie fra
        # i noti) e quando la battuta e' finita (parlato intero, si impara e
        # semmai si iscrive qualcuno). Per il secondo momento l'audio va tenuto,
        # e finora la pipeline lo lasciava passare: da qui l'anello.
        self.tracker: SpeakerTracker | None = (
            SpeakerTracker(cfg.speaker) if cfg.speaker.backend != "none" else None
        )
        self._embedder = None  # costruito alla prima battuta: scarica il modello
        self._voices = RingBuffer(
            capacity=int(cfg.audio.ring_seconds * samplerate),
            channels=1,
            samplerate=samplerate,
        )
        self._ring_t0: float | None = None  # tempo del primo campione scritto
        # (quanti campioni c'erano, che ora era) a ogni blocco: la linea
        # temporale dell'anello. Ne bastano quante ne copre la memoria.
        from collections import deque as _deque

        self._marche: "_deque[tuple[int, float]]" = _deque(
            maxlen=max(64, int(cfg.audio.ring_seconds * 200))
        )
        # **L'attacco della voce, non la comparsa del testo.** Nell'esperimento
        # che ha prodotto i gruppi confermati all'ascolto il ritaglio partiva
        # dall'onset del VAD piu' vicino al sottotitolo; nella pipeline partiva
        # da `t_on`. E' l'unica differenza fra i due, e i due danno risultati
        # diversi: il testo compare quando il gioco decide di mostrarlo, la voce
        # comincia quando il personaggio apre la bocca, e mezzo secondo di
        # scarto su un ritaglio da un secondo e mezzo vuol dire un terzo di
        # ritaglio preso dal personaggio precedente. Un centroide costruito su
        # ritagli cosi' non e' sporco: e' di due persone.
        self._vad = make_vad(cfg.vad, samplerate) if self.tracker is not None else None
        self._onsets: list[float] = []
        self._da_dire: list[SubtitleEvent] = []  # battute in attesa di sapere chi parla
        # **Il registro delle impronte, spento di suo.** Chi lo accende (il
        # banco, `tools/dub.py --dump-speaker`) ci trova dentro l'intero ingresso
        # del tracker: l'impronta breve con cui si e' scelta la voce e quella
        # intera da cui si e' imparato. Con quelle due un raggruppamento diverso
        # si prova in millisecondi invece che in una passata di OCR — lo stesso
        # rapporto che c'e' fra `replay --dump-reads` e `tools/retrack.py`, e per
        # la stessa ragione: due tarature confrontate su due esecuzioni diverse
        # sarebbero confrontate anche su tutto il rumore che le separa.
        self.speaker_log = None  # file di testo aperto, una riga JSON per evento

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
        # **Il passo lo dichiara il motore, non la sessione.** Quello di config
        # e' il punto di partenza per un backend che non lo sappia dire; usarlo
        # comunque significherebbe stimare le durate di SuperTonic col ritmo di
        # Piper, e quel numero decide quanta fretta chiedere prima di
        # sintetizzare.
        self._cps = float(getattr(tts, "chars_per_second", cfg.tts.chars_per_second))
        self._cps_n = 0
        # Quanto chiedere in piu' al sintetizzatore per ottenere la velocita'
        # voluta. Parte da 1 e si impara: `length_scale` non e' proporzionale,
        # e senza questa correzione il tetto sulla velocita' resta un desiderio.
        self._native_gain = 1.0
        # **Il motore sa consegnare a pezzi?** Se si', la battuta si programma
        # prima di esistere e i campioni la raggiungono mentre suona. Lo decide
        # `speak.base.sa_streaming`, cioe' il backend piu' `tts.stream` di config.
        self._streaming = sa_streaming(tts)
        # **Siamo sul banco?** Lo dice l'orologio: virtuale vuol dire che il tempo
        # avanza a comando e non a muro. Serve solo allo streaming, che con un
        # orologio virtuale non puo' consegnare in tempo per costruzione.
        self._banco = isinstance(self.clock, VirtualClock)
        # Un produttore alla volta. **Non e' prudenza, e' aritmetica**: il modello
        # sta avanti al tempo reale con un margine del 20% (0,83x misurato), e due
        # generazioni che si contendono la stessa GPU lo perdono tutte e due. La
        # battuta dopo, del resto, non serve finche' la precedente non ha finito
        # di suonare.
        self._turno_sintesi = threading.Lock()
        self._produttori: list[threading.Thread] = []
        self._t_primo = self.metrics.timer("speak.first_sample")
        self._n_stream_rotto = self.metrics.counter("speak.stream_failed")
        # Quante battute hanno avuto il nome **dal gioco** invece che dall'audio.
        # Se resta a zero con `label.enabled` acceso, il formato dichiarato non
        # corrisponde a quello che il gioco scrive — ed e' l'unico modo di
        # accorgersene senza stare a guardare i sottotitoli a uno a uno.
        self._n_etichette = self.metrics.counter("vision.label.hit")
        self._t_backlog = self.metrics.timer("dub.backlog")
        self._t_rate = self.metrics.timer("dub.rate_x1000")
        self._t_hurry = self.metrics.timer("dub.hurry_x1000")
        self._t_nativo = self.metrics.timer("dub.native_x1000")
        self._n_collision = self.metrics.counter("dub.collision")
        self._n_overflow = self.metrics.counter("dub.overflow")
        self._t_synth = self.metrics.timer("speak.synth")
        self._t_latency = self.metrics.timer("dub.latency")
        self._t_live = self.metrics.timer("dub.latency_live")
        self._t_embed = self.metrics.timer("speaker.embed")
        self._n_speakers = self.metrics.counter("speaker.new")
        self._n_merged = self.metrics.counter("speaker.merged")
        self._n_neutra = self.metrics.counter("speaker.voce_neutra")
        self._n_no_clip = self.metrics.counter("speaker.no_clip")
        # Quanto l'anello e' indietro rispetto all'orologio: zero sul banco per
        # costruzione, dal vivo e' la distanza fra "adesso" e "cio' che si e'
        # sentito". E' il numero che mancava per capire perche' il vivo
        # riconoscesse peggio del banco, e adesso si legge in ogni sessione.
        self._t_ring_lag = self.metrics.timer("speaker.ring_lag")
        self._t_scarto_onset = self.metrics.timer("speaker.onset_offset")
        self._n_repeated = self.metrics.counter("dub.repeated")
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
            #
            # **E la neutra insieme alle altre, che e' quella che parla per
            # prima.** Non sta nel pool — apposta, perche' nessuno se la tenga —
            # e proprio per questo il ciclo qui sopra la saltava. Ma da quando le
            # decisioni sotto soglia sono anonime, la voce d'apertura di ogni
            # sessione **e' lei**: quindici battute su diciotto nei primi trenta
            # secondi. Scaldare tutto il pool tranne l'unica voce che parlera'
            # per prima e' il difetto di sempre, spostato di un posto ancora.
            for voce in [*self.pool.voices, self._neutra]:
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
            self._learn(ev)
        # **Non si parla subito: si aspetta che il personaggio parli.** Alla
        # comparsa del sottotitolo la sua voce non ha ancora emesso un suono, e
        # decidere li' vuol dire decidere sull'audio del personaggio precedente.
        # Misurato: con attesa zero uno dei tre personaggi della scena riceveva
        # la voce giusta **zero volte su ventidue**. Si veda
        # `SpeakerConfig.decide_after_ms`, dove sta la tabella.
        # **La lettura che migliora mentre la battuta aspetta il suo turno.**
        # Fra la conferma e la voce passa mezzo secondo (`decide_after_ms`), ed
        # e' esattamente il tempo in cui l'OCR finisce di leggere un sottotitolo
        # comparso in dissolvenza. Senza queste due righe si diceva il frammento
        # confermato per primo mentre il lettore aveva gia' la frase intera: non
        # un doppione — quello lo chiude il cancello — ma **la versione peggiore
        # di una battuta detta una volta sola**, che nessun contatore mostrava.
        if out.updated and self._da_dire:
            sostituisci = {id(vecchio): nuovo for vecchio, nuovo in out.updated}
            self._da_dire = [sostituisci.get(id(ev), ev) for ev in self._da_dire]
        self._da_dire.extend(ev for ev in out.opened if ev.text.strip())
        if self.tracker is None:
            pronte, self._da_dire = self._da_dire, []
        else:
            # **Si aspetta l'audio, non l'orologio.** L'attesa esiste per un
            # motivo solo: avere mezzo secondo del parlato di questo personaggio
            # da dare all'impronta. Misurarla sul muro presuppone che il muro e
            # l'anello vadano insieme — vero sul banco, dove l'audio di un
            # pacchetto entra prima del suo frame, falso dal vivo, dove il thread
            # audio scrive al ritmo del device. Li' l'attesa scadeva mentre
            # l'audio non c'era ancora, e la decisione si prendeva su un ritaglio
            # troncato.
            #
            # La valvola c'e' ed e' `max_wait_ms`: se l'audio non arriva, dopo
            # quel tanto si parla lo stesso. Una battuta detta male e' un
            # difetto, una battuta non detta e' un buco — e un anello fermo
            # (device staccato, sessione finita male) non deve poter zittire
            # tutto il doppiaggio.
            attesa = self.cfg.speaker.decide_after_ms / 1000.0
            limite = attesa + self.cfg.speaker.max_wait_ms / 1000.0
            udito = self.udito_fino_a
            ora = self.clock.now()

            def pronta(e: SubtitleEvent) -> bool:
                # **Se il gioco dice chi parla, non c'e' niente da aspettare.**
                # L'attesa serve ad avere mezzo secondo di parlato da dare
                # all'impronta; con il nome scritto a schermo l'impronta non si
                # calcola nemmeno, quindi aspettarla sarebbe pagare 500 ms per una
                # domanda a cui si e' gia' risposto. E' tutto il guadagno di
                # questa feature, e sta in questa riga.
                if self._etichetta(e) is not None:
                    return True
                if udito is not None and udito - e.t_on >= attesa:
                    return True
                return ora - e.t_on >= limite

            pronte = [e for e in self._da_dire if pronta(e)]
            self._da_dire = [e for e in self._da_dire if not pronta(e)]
        return [self._speak(ev) for ev in pronte if not self._gia_detta(ev)]

    def _speak(self, event: SubtitleEvent) -> SpokenLine:
        """Da battuta letta a audio programmato."""
        decisione = self._speaker_for(event)
        # **Il nome non si pronuncia.** Leggere ad alta voce «Franklin due punti
        # come va bello» sarebbe peggio che non avere l'etichetta: si toglie il
        # prefisso da tutto cio' che viene dopo — durata prevista, sintesi, log —
        # rilegando l'evento. La deduplica invece e' gia' avvenuta sul testo
        # grezzo, in `_pronte`, quindi confronta sempre mele con mele.
        etichetta = self._etichetta(event)
        if etichetta is not None and etichetta.testo != event.text:
            event = replace(event, text=etichetta.testo)
        speaker_id = decisione.speaker_id
        # Il sesso della voce arriva dall'intonazione misurata sulle battute
        # intere di questo personaggio. Senza, il pool alterna maschile e
        # femminile — giusto quando non si sa niente, sbagliato appena si sa — e
        # in una scena di tre uomini uno di loro parla con la voce di una donna.
        p = self.tracker.get(speaker_id) if self.tracker is not None else None
        voice = self._voce_per(speaker_id, p, event.t_on, anonima=decisione.anonima)

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
        stima = n / max(1e-6, self._cps)
        if self.cfg.tts.native_rate_max > 1.0:
            # **Si mira all'istante in cui la voce partira' davvero, non a
            # adesso.** I due `plan` di questa funzione usavano due `elapsed`
            # diversi: qui il tempo passato *finora*, piu' sotto quello fino
            # all'attacco vero — che comprende la sintesi appena fatta e la coda.
            # Il secondo budget e' quindi sempre piu' stretto del primo, e la
            # battuta veniva accelerata per stare in una finestra piu' larga di
            # quella in cui poi doveva stare davvero. Il residuo cadeva su WSOLA,
            # cioe' sulla leva che schiaccia invece di articolare: misurato, la
            # compressione mediana restava a 1,098 con un quarto delle battute al
            # tetto anche quando la voce nativa stava facendo il suo lavoro.
            #
            # La sintesi non e' ancora avvenuta, quindi il suo costo si stima
            # dalla media di quelle passate — e la coda invece e' un fatto, sta
            # gia' scritta in `_free_at`.
            costo_sintesi = self._t_synth.mean / 1000.0 if self._t_synth.count else 0.0
            inizio_atteso = max(self.clock.now() + costo_sintesi, self._free_at)
            budget = self.timing.plan(
                event.text, stima, elapsed=max(0.0, inizio_atteso - event.t_on)
            ).budget
            if budget <= 0.05:
                # Finestra gia' finita: si e' comunque in ritardo, e allora tanto
                # vale che a parlare svelto sia il sintetizzatore invece di
                # WSOLA. E' il caso in cui la differenza fra le due si sente di
                # piu', perche' e' quello in cui si accelera di piu'.
                nativo = self.cfg.tts.native_rate_max
            elif stima > budget:
                nativo = min(self.cfg.tts.native_rate_max, stima / budget)

        # **Si chiede di piu' di quanto si vuole, perche' il sintetizzatore ne
        # consegna di meno.** `length_scale` di Piper non e' proporzionale:
        # chiedendo 1,45 la battuta si accorcia molto meno di quanto quel numero
        # promette, e finora io lo chiedevo a occhi chiusi senza mai controllare
        # cosa fosse arrivato. Il tetto vale su cio' che si **ottiene**, quindi
        # la richiesta va corretta del divario misurato.
        richiesta = min(nativo * self._native_gain, 3.0) if nativo > 1.0 else 1.0

        if self._streaming:
            return self._speak_streaming(
                event, voice, decisione, p, stima=stima, richiesta=richiesta
            )

        t0 = time.perf_counter()
        speech = self.tts.synthesize(event.text, voice, rate=richiesta)
        synth_ms = (time.perf_counter() - t0) * 1000.0
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
        elif nativo > 1.0 and audio.size and n >= 8:
            # **L'anello si chiude qui.** `stima` e' quanto sarebbe durata al
            # naturale, quindi `stima / durata` e' l'accelerazione davvero
            # ottenuta. Se avevo chiesto `richiesta` e ne e' arrivata meno, il
            # divario entra nel guadagno e la prossima volta si chiede di piu'.
            # Senza questo anello il tetto sulla velocita' e' un desiderio.
            ottenuto = stima / max(1e-6, len(audio) / self.samplerate)
            if ottenuto > 0.5:
                # **Il divario si misura contro il bersaglio, non contro la
                # richiesta.** Era `richiesta / ottenuto`, e quel rapporto ha un
                # punto fisso perverso: si azzera quando `ottenuto` raggiunge la
                # *richiesta*, che a sua volta e' `bersaglio * guadagno`. Cioe'
                # l'anello si dava da solo il bersaglio, e ogni volta che la
                # voce restava indietro alzava sia il guadagno sia il traguardo
                # da raggiungere. Misurato: con `nativo` a 1,20 la voce
                # consegnava **1,70**, e con il tetto a 1,20 consegnava 1,47 —
                # numeri che la configurazione non aveva mai chiesto. Non e' un
                # correttore che gira in un verso solo, e' un correttore che
                # insegue la propria uscita.
                #
                # Contro `nativo` il punto fisso e' quello dichiarato: si
                # consegna l'accelerazione che serve a far stare la battuta nella
                # sua finestra, e nulla di piu'. Quel "nulla di piu'" e' tutto il
                # punto — l'accelerazione non chiesta e' voce che corre.
                divario = nativo / max(ottenuto, 1e-6)
                # **Il limite basso era 1,0, e rendeva il tetto un desiderio.**
                # L'anello poteva solo chiedere *piu'* del bersaglio, mai meno:
                # nato per correggere Piper che consegna meno di quanto promette,
                # non prevedeva il caso opposto. Misurato abbassando il tetto a
                # 1,20: l'accelerazione ottenuta restava a 1,47, cioe' un quarto
                # oltre il tetto, con il guadagno inchiodato al suo minimo. Non
                # dava errore — dava una voce che corre mentre la configurazione
                # dice che non deve. Un correttore che sa girare in un verso solo
                # non e' un correttore, e' un acceleratore.
                # **Il passo dell'anello e' mezzo e non tre decimi, e si vede
                # nei percentili.** Con 0,3 l'accelerazione consegnata su una
                # scena da 44 battute stava a 1,16 di mediana e 1,43 al p95:
                # convergeva, ma solo verso la fine, e la prima meta' della scena
                # pagava la lentezza dell'anello invece che quella della voce.
                # Una scena dura un minuto: chi impara in cinquanta battute
                # impara dopo.
                self._native_gain = float(
                    np.clip(self._native_gain * (1.0 + 0.5 * (divario - 1.0)), 0.55, 3.0)
                )
            self._t_nativo.add(ottenuto * 1000.0)

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
            # **La pausa di respiro non si paga quando si e' gia' in ritardo.**
            # `gap_seconds` esiste perche' due battute attaccate suonano come
            # una frase sola, e in un dialogo fanno sembrare che parli sempre la
            # stessa persona. Ma finora si aggiungeva dopo *ogni* battuta, anche
            # quando la successiva stava gia' aspettando in coda: centoventi
            # millisecondi di silenzio deliberato mentre si e' indietro di un
            # secondo. Se la battuta e' partita in ritardo, la pausa e' un lusso
            # e si toglie.
            in_ritardo = t_start > now + 0.05
            respiro = 0.0 if in_ritardo else self.cfg.tts.gap_seconds
            self._free_at = t_start + len(audio) / self.samplerate + respiro
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
        # **La traccia: una riga per battuta con tutto quello che le e'
        # successo, dal frame all'altoparlante.**
        #
        # Serve a una cosa sola e vale la pena dirla, perche' decide anche la
        # forma: confrontare **la stessa battuta** fra banco e vivo stadio per
        # stadio. Finora ogni difetto del vivo e' stato trovato cosi' — il
        # ritaglio troncato, la deriva dell'anello — ma ogni volta mancava un
        # numero e ci voleva un'altra sessione per averlo. Qui ci sono tutti in
        # una volta.
        #
        # **Per battuta e non per frame, ed e' una scelta di merito, non di
        # comodo.** Il dominio audio gira ogni dieci millisecondi: scrivere una
        # riga li' dentro vorrebbe dire perdere campioni, cioe' ricreare
        # esattamente il difetto che ha rovinato tre sessioni. Una misura che
        # disturba cio' che misura non e' una misura. Qui si scrive quando la
        # battuta e' gia' decisa: una riga ogni due secondi, che non si sente.
        udito = self.udito_fino_a
        self._registra_riga(
            {
                "kind": "detta",
                "t_on": round(event.t_on, 3),
                "t_off": None if event.t_off is None else round(event.t_off, 3),
                "text": event.text,
                "cls": event.cls.value,
                # chi parla
                "speaker": speaker_id,
                "anonima": bool(decisione.anonima),
                "punteggio": round(float(decisione.confidence), 3),
                "genere": getattr(p, "gender", "?") if p is not None else "?",
                "f0": round(getattr(p, "f0", 0.0), 1) if p is not None else 0.0,
                "battute_note": getattr(p, "battute", 0) if p is not None else 0,
                "identita_vive": len(self.tracker) if self.tracker is not None else 0,
                # il segnale su cui si e' deciso
                "ritardo_anello": None if udito is None else round(self.clock.now() - udito, 3),
                # **Quanto il mixer e' indietro rispetto all'orologio.** Positivo
                # vuol dire che la voce si sentira' piu' tardi di quanto dice
                # `latenza_ms`: quel numero e' l'istante in cui la battuta era
                # pronta, non quello in cui e' uscita. Era la misura mancante.
                "divario_mixer": round(self.clock.now() - self.mixer.now, 3),
                # la voce e il tempo
                "voce": voice.voice_id,
                "nativo_chiesto": round(float(richiesta), 3),
                "nativo_ottenuto": round(float(stima / max(1e-6, len(audio) / self.samplerate)), 3)
                if audio.size
                else 0.0,
                "wsola": round(float(rate), 3),
                "synth_ms": round(synth_ms, 1),
                "coda_ms": round((t_start - now) * 1000.0, 1),
                "latenza_ms": round(line.latency_ms, 1),
                "durata": round(line.duration, 3),
                "durata_naturale": round(stima, 3),
                "finestra_prevista": round(self.timing.predict(event.text), 3),
                "cps": round(self._cps, 2),
                "guadagno_nativo": round(self._native_gain, 3),
            }
        )
        return line

    def _speak_streaming(
        self,
        event: SubtitleEvent,
        voice,
        decisione: Decisione,
        p,
        *,
        stima: float,
        richiesta: float,
    ) -> SpokenLine:
        """La battuta si programma **prima di esistere**, e i campioni la
        raggiungono mentre suona.

        ## Perche' l'ordine si rovescia

        La catena normale fa: sintetizza, misura la durata, calcola la fretta,
        programma. Con un motore autoregressivo quel primo passo costa **4,9
        secondi** — la battuta e' finita da un pezzo a schermo. In streaming il
        primo blocco arriva dopo ~270 ms, ma quando arriva la durata totale non
        esiste ancora: la si conoscera' quando il modello avra' finito, cioe'
        troppo tardi per servire a programmare.

        Quindi si programma su una **previsione**, `n / chars_per_second`, ed e'
        una previsione debole per costruzione — su Qwen il passo misurato varia
        fra 9,0 e 14,8 car/s perche' il modello campiona. Va bene lo stesso, e per
        la stessa ragione per cui va bene che `D = a + b*n` abbia R2 0,15: chi
        stima qui **non decide**, prepara. A raccogliere lo scarto c'e' `hurry`,
        che su una battuta aperta lavora sulla durata attesa e non su quella
        presente — e c'e' `mix.underrun`, che conta le volte in cui la previsione
        ha sbagliato dalla parte che si sente.

        ## Un produttore alla volta

        Il modello sta avanti al tempo reale con un margine misurato del 17%
        (0,83x, rivocodifiche comprese). Due battute generate insieme si spartiscono
        la stessa GPU e lo perdono tutte e due, quindi il produttore prende un
        turno. Non e' una coda che rallenta niente: la battuta dopo comincia a
        suonare quando questa ha finito, e per allora il turno e' libero.

        ## Cosa **non** succede qui

        Non si impara `chars_per_second` dalla durata ottenuta, e non si chiude
        l'anello di `_native_gain`. Tutti e due misurano quanto il motore ha
        obbedito alla fretta chiesta, e questo motore la fretta non la sa prendere:
        `rate` gli arriva e lo ignora. Un anello che corregge in base a una leva
        scollegata non converge, si sposta — ed e' esattamente il difetto che
        `_native_gain` ha gia' avuto una volta, quando inseguiva la propria uscita.
        """
        now = self.clock.now()
        t_start = max(now, self.mixer.now, self._free_at)
        self._t_backlog.add((t_start - now) * 1000.0)

        # Il budget, sulla durata **prevista**: e' l'unica che esista adesso.
        piano = self.timing.plan(event.text, stima, elapsed=t_start - event.t_on)
        bersaglio = max(piano.budget, stima / self.cfg.timing.rate_max)
        rate = 1.0
        if stima > bersaglio + 1e-3:
            rate = float(
                np.clip(stima / max(bersaglio, 1e-6), 1.0, self.cfg.timing.rate_max)
            )
        self._t_rate.add(rate * 1000.0)
        if piano.overflow > 0:
            self._n_overflow.inc()

        item = self.mixer.schedule(
            np.zeros(0, np.float32),
            t_start,
            speaker_id=decisione.speaker_id,
            text=event.text,
            rate=rate,
            aperta=True,
            durata_attesa=stima,
        )

        line = SpokenLine(
            text=event.text,
            speaker_id=decisione.speaker_id,
            voice_id=voice.voice_id,
            cls=event.cls.value,
            t_subtitle=event.t_on,
            t_scheduled=t_start,
            synth_ms=0.0,
            duration=stima / rate,
            rate=rate,
        )

        # **La frequenza del motore non e' quella del mixer**, e in streaming la
        # conversione non e' una riga di passaggio come nel ramo normale.
        #
        # Li' si ricampiona l'array intero una volta (`speech.samplerate !=
        # self.samplerate`, poco piu' su). Qui gli array sono tanti, e
        # ricampionarli uno per uno lascerebbe a ogni giuntura una frazione di
        # campione: da 22050 a 48000 il rapporto non e' intero, e i resti si
        # sommano. Si ricampiona quindi **la battuta fin qui** e si consegna solo
        # la coda nuova — la stessa forma che `QwenTts.stream` usa un piano piu'
        # sotto, e per lo stesso motivo.
        #
        # Saltare del tutto questa conversione non da' errore, ed e' il punto: la
        # prima versione lo faceva, versava campioni a 22050 in un mixer a 48000 e
        # ne usciva un doppiaggio a 2,2x — voce da scoiattolo, e nei log un passo
        # di 30 caratteri al secondo dove il motore ne fa 12. Nessun contatore lo
        # diceva; a dirlo e' stato che *quel* numero era impossibile.
        # **La prenotazione parte dalla previsione e si corregge dentro il
        # produttore.** Serve un numero *adesso* — la battuta dopo puo' arrivare
        # fra un frame — e sbagliarlo corto vuol dire farla partire sopra questa.
        in_ritardo = t_start > now + 0.05
        respiro = 0.0 if in_ritardo else self.cfg.tts.gap_seconds
        self._free_at = t_start + stima / rate + respiro

        grezzi: list[np.ndarray] = []
        convertiti = 0

        def converti(blocco: np.ndarray) -> np.ndarray:
            if self.tts.samplerate == self.samplerate:
                return blocco
            from mix.stretch import resample

            nonlocal convertiti
            grezzi.append(blocco)
            intero = resample(
                np.concatenate(grezzi), self.tts.samplerate, self.samplerate
            )
            pezzo = intero[convertiti:]
            convertiti = len(intero)
            return pezzo

        def produci() -> None:
            t0 = time.perf_counter()
            primo = True
            with self._turno_sintesi:  # noqa: SIM117 - un turno alla volta, si veda sopra
                if item.annullata:
                    return
                try:
                    # Il tetto e' **largo**: tre volte la previsione piu' un
                    # secondo. Deve prendere il modello che si incanta e non
                    # toccare mai una frase lunga detta piano.
                    flusso = self.tts.stream(
                        event.text, voice, rate=richiesta, max_seconds=3.0 * stima + 1.0
                    )
                    for grezzo, finita in flusso:
                        if item.annullata:
                            return
                        blocco = converti(grezzo)
                        self.mixer.append(item, blocco, chiudi=finita)
                        # **La prenotazione si corregge man mano.** `_free_at` e'
                        # stato preso sulla durata *prevista*; se la battuta vera
                        # e' piu' lunga, la successiva e' gia' stata programmata
                        # sopra questa — due voci italiane insieme, che e' il
                        # difetto peggiore del prodotto. Misurato: una battuta di
                        # quindici caratteri ha prodotto 9,12 s di audio (il
                        # modello si e' incantato), contro 1,04 previsti.
                        #
                        # `finisce_a` guarda gia' anche cio' che e' arrivato, e la
                        # coda e' l'unica cosa che sa la verita': si prende da li'.
                        self._free_at = max(self._free_at, self.mixer.finisce_a + respiro)
                        if primo and blocco.size:
                            primo = False
                            ms = (time.perf_counter() - t0) * 1000.0
                            self._t_primo.add(ms)
                            # `synth_ms` in streaming e' **il tempo al primo
                            # campione**, non il costo della battuta. E' quello che
                            # si sente, ed e' l'unico che `live_latency_ms` puo'
                            # sommare senza mentire: il resto della sintesi avviene
                            # mentre la voce gia' parla.
                            line.synth_ms = ms
                        if finita:
                            break
                except Exception as e:  # pragma: no cover - dipende dal motore
                    # **Si conta, non solo si stampa.** Una battuta che muore qui
                    # esce come silenzio: la catena non se ne accorge, il mixer
                    # chiude un array vuoto e il log dice "detta". E' la forma
                    # esatta del ripiego che non si dichiara — e ci sono gia'
                    # cascato in questa sessione, quando un parametro nuovo nella
                    # firma di `stream()` ha trasformato sette verifiche in zero
                    # campioni invece che in un errore.
                    self._n_stream_rotto.inc()
                    print(f"streaming: battuta interrotta: {e!r}", file=sys.stderr)
                finally:
                    self.mixer.append(item, np.zeros(0, np.float32), chiudi=True)
            ms_tot = (time.perf_counter() - t0) * 1000.0
            self._t_synth.add(ms_tot)
            line.duration = len(item.audio) / self.samplerate

            # **Il passo si impara anche qui, e qui e' piu' onesto che altrove.**
            # Nel ramo normale si impara solo dalle battute a cui non e' stata
            # chiesta fretta, perche' altrimenti si misurerebbe quanto il motore
            # ha obbedito invece di quanto parla in fretta. In streaming quel
            # dubbio non c'e': la compressione l'ha applicata il mixer, di un
            # fattore che conosciamo esattamente (`rate`), e il motore la fretta
            # non la prende affatto. Dividendolo via resta la durata naturale.
            #
            # Serve: `chars_per_second` decide `stima`, e in streaming `stima`
            # non e' piu' solo la fretta da chiedere — e' la **prenotazione**
            # della coda. Sbagliarla del venti per cento sposta ogni battuta
            # successiva.
            n_car = spoken_length(event.text)
            naturale = line.duration * rate
            if n_car >= 8 and naturale > 0.2:
                misurato = n_car / naturale
                self._cps_n += 1
                self._cps += min(0.25, 1.0 / self._cps_n) * (misurato - self._cps)

        if self._banco:
            # **Sul banco il produttore gira qui, non in un thread, e la ragione e'
            # la stessa per cui `--tempo-reale` esiste.** Con l'orologio virtuale
            # il tempo del media avanza a comando, quaranta volte piu' in fretta
            # del muro: il thread audio versa tutta la battuta prima che il thread
            # di sintesi abbia consegnato il secondo blocco, e cio' che si
            # registrerebbe sarebbe silenzio con `mix.underrun` alle stelle. Non
            # sarebbe un difetto dello streaming, sarebbe **il banco che non puo'
            # esprimere la domanda** — lo stesso motivo per cui la sintesi
            # spostata fuori dal thread video sembrava valere -745 ms.
            #
            # Girando qui, l'audio prodotto e' esattamente quello del vivo (lo
            # verifica `bench_qwen --pezzi`: i blocchi concatenati sono la battuta
            # intera), e cio' che il banco smette di poter dire — il tempo al primo
            # campione — e' precisamente cio' che non saprebbe dire comunque.
            produci()
        else:
            t = threading.Thread(target=produci, name="tts-stream", daemon=True)
            self._produttori = [x for x in self._produttori if x.is_alive()]
            self._produttori.append(t)
            t.start()

        self._n_lines.inc()

        self._t_latency.add(line.latency_ms)
        self._t_live.add(line.live_latency_ms)
        self.spoken.append(line)
        udito = self.udito_fino_a
        self._registra_riga(
            {
                "kind": "detta",
                "t_on": round(event.t_on, 3),
                "t_off": None if event.t_off is None else round(event.t_off, 3),
                "text": event.text,
                "cls": event.cls.value,
                "speaker": decisione.speaker_id,
                "anonima": bool(decisione.anonima),
                "punteggio": round(float(decisione.confidence), 3),
                "genere": getattr(p, "gender", "?") if p is not None else "?",
                "f0": round(getattr(p, "f0", 0.0), 1) if p is not None else 0.0,
                "battute_note": getattr(p, "battute", 0) if p is not None else 0,
                "identita_vive": len(self.tracker) if self.tracker is not None else 0,
                "ritardo_anello": None if udito is None else round(self.clock.now() - udito, 3),
                "divario_mixer": round(self.clock.now() - self.mixer.now, 3),
                "voce": voice.voice_id,
                "nativo_chiesto": round(float(richiesta), 3),
                # In streaming non si misura: la durata ottenuta non esiste ancora
                # quando questa riga si scrive, e scrivere zero e' meno peggio che
                # scrivere un numero che sembra una misura.
                "nativo_ottenuto": 0.0,
                "wsola": round(float(rate), 3),
                "synth_ms": 0.0,  # si legge in `speak.first_sample`, non qui
                "streaming": True,
                "coda_ms": round((t_start - now) * 1000.0, 1),
                "latenza_ms": round(line.latency_ms, 1),
                "durata": round(line.duration, 3),
                "durata_naturale": round(stima, 3),
                "finestra_prevista": round(self.timing.predict(event.text), 3),
                "cps": round(self._cps, 2),
                "guadagno_nativo": round(self._native_gain, 3),
            }
        )
        return line

    def _gia_detta(self, event: SubtitleEvent) -> bool:
        """Questa frase e' gia' stata pronunciata un attimo fa?

        E' l'ultimo cancello, e l'unico che vale per **tutti** i modi in cui una
        battuta puo' essere riaperta: la sparizione creduta troppo in fretta, la
        sostituzione, una rilettura che migliora a meta'. Ognuno ha la sua cura a
        monte; questo li taglia tutti nel punto in cui il difetto smette di
        essere una riga di log e diventa una voce che si sente.

        **Due domande, non una.** Il rapporto prende le riletture che si
        somigliano; il contenimento prende quelle in cui una e' un pezzo
        dell'altra, che sono la forma prevalente e che il rapporto non vede —
        misurato su una sessione dal vivo, il cancello a solo rapporto ne
        prendeva zero su tredici. Quelle tredici valevano 15,2 secondi di
        parlato ridetto su 140, e sono la causa dell'accumulo di coda: dopo una
        battuta letta tre volte l'arretrato arrivava a 4,6 secondi e ci metteva
        ventidue secondi a rientrare.

        **Il prezzo, dichiarato**: quando la rilettura e' la versione *buona* di
        un frammento gia' detto — l'OCR ha preso mezza frase, poi tutta — qui si
        perde il resto della frase. La cura vera sta a monte, in
        `SubtitleTracker`, dove la battuta non viene riaperta affatto e il testo
        si aggiorna sul posto; questo cancello vede solo cio' che e' sfuggito, e
        li' dire meno e' meglio che dire due volte.
        """
        cfg = self.cfg.repeat
        if not cfg.enabled:
            return False
        chiave = _lettere(event.text)
        if not chiave:
            return False
        for riga in reversed(self.spoken):
            if event.t_on - riga.t_subtitle > cfg.window_s:
                break  # `spoken` e' in ordine di tempo: piu' indietro e' solo piu' vecchio
            altra = _lettere(riga.text)
            if not altra:
                continue
            if SequenceMatcher(None, chiave, altra).ratio() >= cfg.similarity:
                self._n_repeated.inc()
                return True
            if (
                min(len(chiave), len(altra)) >= cfg.containment_min_chars
                and contenimento(chiave, altra) >= cfg.containment
            ):
                self._n_repeated.inc()
                return True
        return False

    def _voce_per(self, speaker_id: str, p, t: float, *, anonima: bool = False):
        """La voce di questa battuta. La politica sta in `speak/pool.py`, perche'
        il banco deve poter rigiocare esattamente questa."""
        voce = voce_per(
            self.pool,
            speaker_id,
            p,
            t,
            neutra=self._neutra,
            defer_max=self.cfg.speaker.gender_defer_max_lines,
            ripiego=self.cfg.speaker.gender_fallback,
            anonima=anonima,
        )
        if voce is self._neutra:
            self._n_neutra.inc()
        return voce

    def _etichetta(self, event: SubtitleEvent):
        """Chi parla secondo il **gioco**, se il gioco lo scrive. Altrimenti `None`.

        Il colore si prende dalla prima riga: un sottotitolo su due righe e' una
        frase andata a capo, quindi il colore e' lo stesso — e se non lo fosse
        sarebbero due eventi, non uno.
        """
        if self.label is None:
            return None
        rgb = event.lines[0].rgb if event.lines else None
        return self.label.leggi(event.text, rgb)

    def _speaker_for(self, event: SubtitleEvent) -> "Decisione":
        """Chi parla, con quel poco che si e' riusciti a sentire finora.

        Il colore della riga **non** entra piu' in questa decisione. Assumeva
        che il grigio fosse un secondo personaggio: misurato su 675 battute
        bianche in 17 sessioni, le grigie sono 15 e nessuna e' dialogo. Un
        vincolo su quel segnale vincolerebbe rumore, e in cambio bruciava una
        voce del pool per `S-grey`.

        Qui si sceglie e basta. Iscrivere un personaggio nuovo con mezzo secondo
        di parlato ne inventerebbe uno a ogni battuta — la somiglianza col
        proprio centroide sta sotto 0,40 tre volte su quattro a 0,30 s, per via
        della durata e non dell'identita' — e all'ascolto sarebbe "la voce
        cambia in continuazione". L'iscrizione avviene in `_learn`, a battuta
        finita.
        """
        # **Il nome dichiarato dal gioco vince su tutto.** Non e' una stima da
        # confrontare con una soglia: e' cio' che il gioco ha scritto. Qui non si
        # calcola nessuna impronta — che e' il secondo pezzo del guadagno, dopo
        # l'attesa saltata in `_pronte`.
        etichetta = self._etichetta(event)
        if etichetta is not None:
            self._n_etichette.inc()
            return Decisione(f"L-{etichetta.nome}", 1.0)
        if self.tracker is None:
            return Decisione("S-grey" if event.cls is LineClass.GREY else "S-white", 0.0)
        # Si guarda **indietro** dalla comparsa del sottotitolo, non avanti: la
        # battuta corrente, in questo istante, non ha ancora un solo campione di
        # audio. Vale 76,5% invece dell'89% che si avrebbe aspettando 150 ms —
        # si veda `SpeakerConfig.lead_ms`, dove il prezzo e' scritto.
        # `self.clock.now()` e non `self.mixer.now`: l'anello e' timbrato col
        # tempo del media, e il mixer ha un orologio suo che parte da zero. Dal
        # vivo i due coincidono, sul banco no — ed e' la seconda volta in questo
        # file che i due tempi si scambiano di posto senza dare errore.
        clip = self._clip(event.t_on - self.cfg.speaker.lead_ms / 1000.0, self.clock.now())
        emb = self._embed(clip)
        d = self.tracker.scegli(emb, t=event.t_on)
        # **Quanto parlato c'era davvero dentro l'impronta.** E' il numero che e'
        # mancato per due sessioni: la curva misurata dice che sotto 0,5 s la
        # somiglianza col proprio centroide crolla, quindi un ritaglio corto e un
        # riconoscitore che sbaglia si assomigliano tantissimo — dall'uscita.
        udito = self.udito_fino_a
        self._registra(
            "scegli", event, emb, deciso=d.speaker_id, anonima=d.anonima,
            durata=0.0 if clip is None else round(len(clip) / self.samplerate, 3),
            ritardo_anello=None if udito is None else round(self.clock.now() - udito, 3),
        )
        return d

    def _learn(self, event: SubtitleEvent) -> None:
        """La battuta e' sparita dallo schermo: adesso il suo audio c'e' tutto.

        E' l'unico punto in cui nasce un personaggio. Non si disdice niente di
        gia' detto — la voce ha gia' parlato — ma la banca migliora, e la
        battuta successiva dello stesso personaggio la trovera' piu' facilmente.
        """
        if self.tracker is None or event.t_off is None:
            return
        inizio = self._onset_vicino(event.t_on)
        # **Di quanto l'attacco del parlato cade dopo la comparsa del testo.**
        # Su registrazione i due istanti coincidono — misurato, mediana -33 e
        # -20 ms — quindi dal vivo questo numero **non e' una proprieta' del
        # gioco: e' il ritardo del percorso audio**, il buffer del device piu'
        # quello di VoiceMeeter. E' l'ultima differenza fra banco e vivo rimasta
        # non misurata, e da qui in poi ogni sessione la porta scritta.
        self._t_scarto_onset.add((inizio - event.t_on) * 1000.0)
        clip = self._clip(inizio, min(event.t_off, inizio + 2.0))
        emb = self._embed(clip)
        if emb is None:
            return
        f0 = stima_f0(clip, self.samplerate) if clip is not None else 0.0
        d = self.tracker.impara(emb, t=event.t_on, f0=f0)
        self._registra(
            "impara", event, emb, f0=round(f0, 2), deciso=d.speaker_id,
            durata=round(len(clip) / self.samplerate, 3),
        )
        if d.is_new:
            self._n_speakers.inc()
        if d.merged is not None:
            # Due identita' erano la stessa persona. Le battute gia' dette
            # restano dette — non si disdice niente — ma da qui in avanti c'e'
            # una voce sola, quella di chi ha parlato di piu'.
            self.pool.merge(*d.merged)
            self._n_merged.inc()

    def _registra_riga(self, record: dict) -> None:
        if self.speaker_log is None:
            return
        self.speaker_log.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.speaker_log.flush()

    def _registra(self, kind: str, event: SubtitleEvent, emb, **extra) -> None:
        """Una riga del registro delle impronte. Non fa niente se e' spento.

        L'impronta si scrive per intero e non riassunta: il banco deve poter
        rifare **la stessa** somiglianza che ha fatto la sessione, e una
        riduzione qualunque cambierebbe di poco tutti i numeri e di molto la
        soglia che se ne ricava.
        """
        if self.speaker_log is None:
            return
        record = {
            "kind": kind,
            "t_on": round(event.t_on, 3),
            "t_off": None if event.t_off is None else round(event.t_off, 3),
            "text": event.text,
            "cls": event.cls.value,
            "emb": None if emb is None else [round(float(v), 6) for v in np.asarray(emb).reshape(-1)],
        }
        record.update(extra)
        self.speaker_log.write(json.dumps(record, ensure_ascii=False) + "\n")

    def _onset_vicino(self, t_on: float, pre: float = 0.5, post: float = 0.8) -> float:
        """L'attacco di parlato piu' vicino alla comparsa del sottotitolo.

        Fuori dalla finestra si torna a `t_on`: un onset a due secondi di
        distanza non e' l'attacco di questa battuta, e agganciarcisi sposterebbe
        il ritaglio **a caso** — un difetto peggiore di quello che cura, e
        indistinguibile all'ascolto da un riconoscimento che sbaglia.
        """
        migliore, distanza = t_on, 1e9
        for t in self._onsets:
            d = abs(t - t_on)
            if -pre <= t - t_on <= post and d < distanza:
                migliore, distanza = t, d
        return migliore

    def _frame_per_tempo(self, t: float) -> int:
        """Il campione che corrisponde all'istante `t`, secondo le marche.

        Fra due marche si interpola, perche' dentro un blocco i campioni sono
        regolari; fuori si estrapola alla frequenza nominale, che e' l'unica cosa
        ragionevole da fare quando quell'audio non e' mai passato di qui.
        """
        if not self._marche:
            return 0
        n0, t0 = self._marche[0]
        if t <= t0:
            return int(round(n0 + (t - t0) * self.samplerate))
        precedente = self._marche[0]
        for marca in self._marche:
            if marca[1] >= t:
                (na, ta), (nb, tb) = precedente, marca
                if tb <= ta:
                    return nb
                quota = (t - ta) / (tb - ta)
                return int(round(na + quota * (nb - na)))
            precedente = marca
        n1, t1 = self._marche[-1]
        return int(round(n1 + (t - t1) * self.samplerate))

    @property
    def udito_fino_a(self) -> float | None:
        """Fino a che istante l'anello contiene davvero audio. `None` se e' vuoto.

        **L'anello ha un orologio suo, e non e' quello del muro.** La sua
        posizione la decidono i campioni entrati, non il tempo passato: e' `t0`
        piu' il conteggio diviso la frequenza. Sul banco le due cose coincidono
        per costruzione — `tools/dub.py` versa l'audio di un pacchetto prima di
        passarne il frame — ma dal vivo i due domini sono due thread e il
        secondo scrive al ritmo del device, con il suo buffer. L'orologio a muro
        e' sempre un po' avanti a cio' che si e' sentito.

        Chiedere audio oltre questo istante non da' errore: `RingBuffer.read_from`
        **tronca** e restituisce cio' che c'e', anche pochi millisecondi. Ed e'
        cosi' che il riconoscimento dal vivo e' andato a fondo — non per la
        latenza, ma perche' l'impronta veniva calcolata su un ritaglio di
        centocinquanta millisecondi credendolo di settecento.
        """
        if not self._marche:
            return None
        return self._marche[-1][1]

    def _clip(self, t_on: float, fino_a: float) -> np.ndarray | None:
        """L'audio del centro fra due istanti, o `None` se non c'e' abbastanza.

        Il centro e non il mixdown: il dialogo sta li', ed e' la stessa
        estrazione che usa il duck. Misurare un segnale diverso da quello che la
        pipeline tratta darebbe un'identita' che vale per un altro audio.

        **Si chiede solo cio' che l'anello ha davvero**, e si controlla quanto e'
        tornato invece di quanto si era chiesto: erano due controlli mancanti che
        insieme facevano passare per buona un'impronta calcolata su un ritaglio
        troncato. Misurato dal vivo, il ritaglio veloce somigliava al proprio
        ritaglio intero 0,45 contro lo 0,69 del banco, e undici volte su
        quarantadue era vuoto del tutto.
        """
        if self._ring_t0 is None:
            return None
        udito = self.udito_fino_a
        if udito is not None:
            # **Quanti campioni non sono mai arrivati**, in millisecondi di
            # audio. E' il numero che conta e che la versione precedente non
            # poteva esprimere: li' si misurava la distanza fra l'orologio e una
            # quantita' definita *come* l'orologio, quindi valeva zero anche in
            # una passata dove un terzo dei frame veniva saltato. Qui invece
            # cresce quando il thread audio resta indietro, che e' l'unico modo
            # in cui l'anello puo' mentire sul tempo.
            atteso = self.clock.now() - (self._ring_t0 or self.clock.now())
            self._t_ring_lag.add(
                max(0.0, atteso - self._voices.written / float(self.samplerate)) * 1000.0
            )
            fino_a = min(fino_a, udito)
        durata = fino_a - t_on
        if durata < 0.20:  # meno di questo non contiene una sillaba intera
            self._n_no_clip.inc()
            return None
        durata = min(durata, 2.0)
        inizio = self._frame_per_tempo(t_on)
        try:
            clip = self._voices.read_from(inizio, int(durata * self.samplerate))
        except (Overrun, ValueError):
            # `Overrun`: l'anello ha girato, la battuta e' piu' vecchia della
            # memoria. `ValueError`: si sta chiedendo audio non ancora scritto.
            # Nessuno dei due e' un errore da propagare — sono una battuta
            # inanalizzabile — ma **restituire audio sbagliato lo sarebbe**, e
            # sarebbe invisibile: darebbe l'impronta di un altro momento, cioe'
            # un personaggio verosimile e sbagliato.
            self._n_no_clip.inc()
            return None
        # E qui la seconda guardia: `read_from` tronca in silenzio quando il
        # produttore non e' arrivato. Un ritaglio corto non e' un ritaglio
        # scadente, e' **un altro esperimento** — la curva misurata dice che a
        # 0,30 s la somiglianza col proprio centroide sta sotto 0,40 tre volte su
        # quattro, e con la soglia dei nomi a 0,30 quel ritaglio non nomina
        # nessuno. Meglio dichiararlo assente che farlo passare per buono.
        if clip.size < int(0.20 * self.samplerate):
            self._n_no_clip.inc()
            return None
        return clip.reshape(-1) if clip.size else None

    def _embed(self, clip: np.ndarray | None):
        """L'impronta del ritaglio. Il modello si carica alla prima richiesta."""
        if clip is None or clip.size == 0 or self.tracker is None:
            return None
        if self._embedder is None:
            from listen.embed import make_embedder

            self._embedder = make_embedder(self.cfg.speaker)
            # **Quale impronta sta girando davvero**, non quella chiesta.
            # `make_embedder` ripiega su `mfcc` se il modello non c'e', e lo
            # dichiara su stderr — che dal vivo, dentro una finestra, non lo
            # legge nessuno. Nel registro invece resta.
            self._registra_riga({"kind": "impronta", "backend": self._embedder.name})
        # Il costo si misura a muro con `perf_counter` e non con l'orologio del
        # media: sul banco il secondo non avanza mentre il modello lavora, e
        # l'impronta risulterebbe gratis proprio dove si vuole sapere se lo e'.
        t0 = time.perf_counter()
        out = self._embedder.embed(clip, self.samplerate)
        self._t_embed.add((time.perf_counter() - t0) * 1000.0)
        return out

    # -- dominio audio -----------------------------------------------------

    def on_audio(self, game: np.ndarray | None, n: int | None = None) -> np.ndarray:
        """Un blocco di audio di gioco. Restituisce il blocco da mandare in uscita.

        Prima di mixare, il centro finisce nell'anello: e' l'unico posto da cui
        il dominio video potra' ripescarlo quando la battuta sara' finita. Si
        scrive **prima** di `process`, perche' `mixer.now` e' il tempo del primo
        campione del blocco e dopo non lo sarebbe piu'.
        """
        if self.tracker is not None and game is not None and getattr(game, "size", 0):
            mono = split(game)[0] if game.ndim == 2 and game.shape[1] == 2 else game.reshape(-1)
            if self._ring_t0 is None:
                # **L'orologio del media, non quello del mixer.** Dal vivo i due
                # coincidono e l'errore non si vedrebbe; sul banco no — il mixer
                # parte da zero mentre le battute sono timbrate al minuto 1240 —
                # e l'anello verrebbe letto a un indice di sessanta milioni.
                # Qui serve la stessa base con cui e' timbrato `t_on`, perche'
                # l'unica cosa che si chiede all'anello e' "dov'era quella
                # battuta".
                self._ring_t0 = self.clock.now()
            mono = mono.astype(np.float32)
            self._voices.write(mono)
            # **Ogni blocco lascia una marca: quanti campioni c'erano e che ora
            # era.** E' la linea temporale dell'anello, e sostituisce un'origine
            # unica per una ragione che ha gia' rotto due volte il riconoscimento.
            #
            # *Prima versione*: origine fissata al primo blocco, posizione data
            # dal conteggio. Fedele solo se i campioni arrivano tutti — e dal
            # vivo il thread audio ne perde l'1,1%, quindi il ritardo cresceva di
            # 11 ms al secondo e a fine sessione la finestra di analisi era
            # altrove.
            #
            # *Seconda versione*: origine fatta scorrere a ogni blocco perche'
            # "l'ultimo campione sia adesso". Toglieva la deriva, ma **rietichetta
            # tutto l'audio** ogni volta che l'orologio corre avanti: un
            # sottotitolo timbrato a `t_on` veniva poi cercato in una linea
            # temporale che nel frattempo si era spostata. Con un terzo dei frame
            # saltati — cioe' quando la macchina fatica, cioe' proprio quando
            # serve — il ritaglio finiva sull'audio sbagliato. E la misura non
            # poteva accorgersene: `ritardo_anello` valeva zero **per
            # costruzione**, perche' era la differenza fra l'orologio e una
            # quantita' definita come l'orologio.
            #
            # Con le marche l'audio scritto all'istante T resta etichettato T per
            # sempre. Una perdita sposta le cose di quanto e' stata la perdita,
            # localmente, e non rietichetta niente di gia' scritto. E il ritardo
            # torna una misura che puo' dire di no: e' la distanza fra adesso e
            # l'ultima marca.
            #
            # Bastano le marche che coprono la memoria dell'anello: piu' indietro
            # l'audio non c'e' comunque piu'.
            #
            # La posizione di un campione la dava il conteggio: `t0 + n/sr`. Il
            # conteggio pero' e' fedele solo se i campioni arrivano tutti — e dal
            # vivo non arrivano. Misurato in sessione: **l'anello perde l'1,1% e
            # il ritardo cresce di 11 ms al secondo**, da 88 ms all'inizio a 770
            # dopo un minuto. Le conseguenze si vedono tutte nella stessa
            # sessione: nella prima meta' il ritaglio veloce somiglia al proprio
            # ritaglio intero 0,637 — quanto il banco, 0,689 — e nella seconda
            # crolla a 0,381, mentre la somiglianza con la battuta *precedente*
            # sale a 0,328. Cioe' la finestra scivola via da chi sta parlando.
            #
            # Riancorando, un blocco perso costa un salto di pochi millisecondi
            # una volta sola, invece di spostare per sempre tutto quello che
            # viene dopo. Il lisciamento serve perche' l'istante di arrivo di un
            # blocco trema di qualche millisecondo, e inseguire il tremore
            # sarebbe un altro modo di sbagliare: la costante di tempo e' circa
            # un secondo, che spegne il tremore e lascia passare una deriva di
            # undici millisecondi al secondo.
            #
            # Sul banco non cambia niente **per costruzione**: li' i campioni ci
            # sono tutti, quindi `now - written/sr` vale sempre `t0` e l'ancora
            # non si muove. Lo dice `speaker.ring_lag`, che resta 0,00 ms.
            self._marche.append((self._voices.written, self.clock.now()))
            if self._vad is not None:
                for seg in self._vad.push(mono, t=self.clock.now()):
                    self._onsets.append(seg.t0)
                aperto = self._vad.current
                if aperto is not None and (not self._onsets or self._onsets[-1] != aperto.t0):
                    # Anche la presa di parola **in corso** conta: la battuta si
                    # decide mentre il personaggio sta ancora parlando, e
                    # aspettare che il VAD la chiuda vorrebbe dire non avere
                    # mai l'onset che serve.
                    self._onsets.append(aperto.t0)
                if len(self._onsets) > 512:
                    del self._onsets[:256]
        # **Che ora e' lo dice l'orologio, non il conteggio dei campioni.** Senza
        # questo argomento il mixer suona in una linea temporale che scivola via
        # da quella in cui le battute sono programmate — si veda `Mixer.process`.
        return self.mixer.process(game, n, t=self.clock.now())

    # -- chiusura ----------------------------------------------------------

    def finish(self) -> None:
        """Chiude le battute ancora a schermo: senza, l'ultima resta senza durata."""
        self.closed.extend(self.reader.close().closed)
        # Le battute ancora in attesa vanno dette comunque: la promessa e' che
        # non si scarta niente, e una battuta trattenuta per scegliere meglio la
        # voce sarebbe il modo piu' assurdo di perderla.
        for ev in self._da_dire:
            self._speak(ev)
        self._da_dire.clear()

    def report(self) -> str:
        righe = [
            f"battute doppiate: {len(self.spoken)}",
            f"personaggi sentiti: {len(self.pool)}",
            "",
            self.tracker.report() if self.tracker is not None else "(tracker spento)",
            "",
            self.pool.report(),
            "",
            self.metrics.report(),
        ]
        return "\n".join(righe)
