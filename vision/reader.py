"""Il dominio video, montato: da un frame a battute confermate.

    frame -> ROI -> diff -> [righe -> classe colore -> OCR] -> merge -> tracker

Le parentesi quadre sono la parte cara, ed e' il diff a decidere se aprirle. Un
sottotitolo resta a schermo per decine di frame: senza quel cancello si
rileggerebbe la stessa battuta cinquanta volte.

Due dettagli che valgono piu' di quanto sembri:

- **le righe colorate non arrivano mai all'OCR.** Vengono riconosciute dal
  colore, che costa una proiezione, e buttate prima del riconoscimento, che
  costa quindici millisecondi. Scartarle dopo darebbe lo stesso risultato al
  prezzo pieno;
- **dopo un cambiamento si rilegge comunque per qualche frame**, anche se il
  diff dice che non si muove piu' nulla. Serve allo stabilizzatore per avere le
  letture concordi che gli servono: un sottotitolo appare in dissolvenza e poi
  resta fermo, quindi le letture di conferma cadono proprio quando il diff tace.

C'e' anche un **rubinetto** (`tap`), che riceve ogni singola alimentazione del
tracker prima che il tracker la veda. Non serve alla pipeline: serve a poterla
studiare. Le letture che arrivano in fondo sono una minoranza scelta dallo
stabilizzatore stesso, quindi giudicarlo dal suo output e' come chiedere a un
imputato di scegliere le prove. Con il rubinetto il flusso si registra una volta
sola — l'OCR e' la parte cara — e da li' lo stabilizzatore si rifa' girare
quante volte si vuole, a costo zero e sullo stesso identico ingresso.
"""

from __future__ import annotations

import time
from typing import Callable

import numpy as np

from core.clock import Clock
from core.config import VisionConfig
from core.metrics import MetricsRegistry
from core.stage import Stage
from core.types import OcrLine, merge_lines
from vision.diff import Change, RoiDiff
from vision.lines import classify_lines
from vision.ocr import NullOcr, OcrBackend, italian_only
from vision.roi import crop
from vision.subtitles import SubtitleTracker, TrackerOutput


class SubtitleReader(Stage):
    """Legge i sottotitoli da una sequenza di frame."""

    def __init__(
        self,
        cfg: VisionConfig,
        ocr: OcrBackend | None = None,
        *,
        metrics: MetricsRegistry | None = None,
        clock: Clock | None = None,
        tap: Callable[[float, list, bool], None] | None = None,
        **kw,
    ) -> None:
        super().__init__("vision.read", metrics=metrics, clock=clock, **kw)
        self.cfg = cfg
        self.ocr = ocr if ocr is not None else NullOcr()
        self.tap = tap
        self.diff = RoiDiff(
            threshold=cfg.diff_threshold,
            stride=cfg.diff_stride,
            ink_min_luma=cfg.grey_min_luma,
            contrast_min=cfg.contrast_min if cfg.use_local_contrast else 0.0,
            contrast_kernel=cfg.contrast_kernel,
            ink_min_columns=cfg.ink_min_columns,
            vanish_frames=cfg.vanish_frames,
        )
        self.tracker = SubtitleTracker(cfg)
        self._recheck = 0
        self._ultima_lettura = float("-inf")  # per `max_ocr_hz`

        m = self.metrics
        self._t_diff = m.timer("vision.diff")
        self._t_classify = m.timer("vision.classify")
        self._t_ocr = m.timer("vision.ocr")
        self._n_ocr = m.counter("vision.ocr.lines")
        self._n_colored = m.counter("vision.lines.colored")
        # **Le righe lette con dentro dell'inchiostro colorato.** Sotto
        # `sat_ink_max` la riga resta dialogo e i pixel saturi vengono tolti dal
        # ritaglio: se erano scenario e' giusto, se erano una parola l'OCR legge
        # una frase **mutilata con l'aria di essere intera**, che e' il difetto
        # peggiore perche' non si annuncia.
        #
        # Misurato sulla scena del concessionario: non capita mai. Le 21 righe
        # sopra il 10% erano sei lampi di scenario da 1-3 frame piu' un obiettivo
        # di missione (`Raggiungi Vespucci Beach.`), e quello la soglia lo prende
        # gia' — il ciano e' il 44% del suo inchiostro. Il caso che sfuggirebbe e'
        # una parola colorata **corta** dentro una frase lunga, che qui non c'e'.
        #
        # Il contatore esiste per quello: rendere visibile un caso che oggi non
        # si puo' distinguere da "non succede". `sat_share` era gia' calcolato e
        # non lo leggeva nessuno.
        self._n_mixed = m.counter("vision.lines.mixed_ink")
        # Quante righe sono state scartate perche' contenevano una **parola**
        # colorata (e non per la quota `sat_ink_max`). Misurato dal vivo, il
        # guadagno non e' dove lo cercavo: non sono gli obiettivi di missione,
        # sono i frammenti di HUD colorata che venivano **incollati** a una
        # battuta vera e pronunciati — `'Rec.Lavoriamo insieme...'`,
        # `"Sì, era lui.Adam'a App"`. Senza questo contatore, "non e' scattato" e
        # "e' spento" sono lo stesso silenzio.
        self._n_color_word = m.counter("vision.lines.color_word")
        self._n_empty = m.counter("vision.ocr.empty")
        self._n_gergo = m.counter("vision.ocr.non_italiano")
        # Il lessico si carica una volta e si dichiara: se la cartella non c'e'
        # il filtro e' **spento**, e va detto invece che scoperto misurando.
        self._lex = None
        if getattr(cfg, "use_lexicon", False):
            from vision.lexicon import carica

            lex = carica(cfg.lexicon_dir)
            self._lex = lex if lex else None
        self._n_opened = m.counter("vision.subtitles.opened")
        self._n_closed = m.counter("vision.subtitles.closed")
        self._n_gated = m.counter("vision.frames.gated")

    def bypass(self, frame=None) -> TrackerOutput:
        return TrackerOutput()

    def process(self, frame: np.ndarray | None) -> TrackerOutput:
        if frame is None:
            return TrackerOutput()
        now = self.clock.now()
        roi = crop(frame, self.cfg.roi)

        t0 = time.perf_counter()
        d = self.diff.update(roi)
        self._t_diff.add((time.perf_counter() - t0) * 1000.0)

        if d.change is Change.VANISHED:
            # Il diff ha visto sparire l'inchiostro: e' una prova indipendente
            # dall'OCR, quindi la chiusura non va rimandata. Rimandarla falsa la
            # durata della battuta, perche' la prossima passata del tracker
            # arriva solo al prossimo cambiamento di schermo, che puo' essere
            # secondi dopo.
            self._recheck = 0
            if self.tap is not None:
                self.tap(now, [], True)
            return self._emit(self.tracker.feed([], now, certain=True))

        if d.changed:
            self._recheck = max(self._recheck, max(1, self.cfg.stable_reads))
        if self._recheck <= 0:
            self._n_gated.inc()
            return TrackerOutput()

        # **Il tetto alla frequenza di lettura, che era dichiarato e non
        # collegato.** `max_ocr_hz` stava in config e non la leggeva nessuno.
        #
        # Il cancello sopra dovrebbe bastare — si legge solo quando la ROI
        # cambia — ma la ROI e' una striscia in mezzo allo schermo e dietro i
        # sottotitoli c'e' il gioco che si muove: misurato su sessanta secondi
        # di scena, 1801 frame, il diff ne ferma 300 e l'OCR gira sugli altri,
        # cioe' a 25 Hz. A 34 ms l'uno fanno **52 secondi di lavoro per 60 di
        # scena**, contro 1,5 secondi di sintesi con Piper e una dozzina con
        # SuperTonic. Il thread video non e' cieco per colpa della sintesi: e'
        # cieco perche' rilegge lo stesso sottotitolo venticinque volte al
        # secondo.
        #
        # **Ma il tetto non vale mentre una candidata aspetta la conferma**, e
        # questa e' la meta' che conta. Le letture non sono tutte uguali: quelle
        # che confermano una battuta nuova sono al massimo `stable_reads` e
        # stanno sul percorso della latenza — rimandarle si sente. Quelle che
        # rileggono per la ventesima volta un sottotitolo gia' a schermo e fermo
        # servono solo a tenerlo vivo e a migliorarne il testo, e possono
        # aspettare un ottavo di secondo. Il tetto colpisce le seconde.
        #
        # La sparizione non passa di qui — il diff la vede e la porta con
        # `certain`, prima di questo cancello — quindi non ritarda nessuna
        # chiusura.
        limite = float(getattr(self.cfg, "max_ocr_hz", 0.0) or 0.0)
        if (
            limite > 0.0
            and not self.tracker.in_attesa
            and (now - self._ultima_lettura) < (1.0 / limite)
        ):
            self._n_gated.inc()
            return TrackerOutput()
        self._recheck -= 1

        t0 = time.perf_counter()
        bands = classify_lines(roi, self.cfg)
        self._t_classify.add((time.perf_counter() - t0) * 1000.0)

        lines: list[OcrLine] = []
        for band in bands:
            if not band.cls.is_dialogue:
                # Scartata dal colore, prima di pagare il riconoscimento.
                self._n_colored.inc()
                if band.color_word:
                    self._n_color_word.inc()
                continue
            # Dialogo, ma con dell'inchiostro colorato tolto dal ritaglio. Meta'
            # della soglia e' abbastanza per non contare il pulviscolo: la
            # mediana delle righe con un po' di saturo e' 0,010, e li' si tratta
            # di scenario entrato nella ROI.
            if band.sat_share >= self.cfg.sat_ink_max / 2.0:
                self._n_mixed.inc()
            t0 = time.perf_counter()
            text, conf = self.ocr.read(band.crop)
            self._t_ocr.add((time.perf_counter() - t0) * 1000.0)
            self._n_ocr.inc()
            # Il tetto si consuma quando il riconoscimento e' stato **pagato**,
            # non quando si e' guardato il frame. Uno schermo senza dialogo non
            # costa niente e non deve rubare il turno alla battuta che comparira'
            # subito dopo.
            self._ultima_lettura = now
            # Prima si toglie cio' che non e' italiano, poi si conta. Il
            # riconoscitore e' addestrato su cinese e inglese e sullo scenario
            # restituisce glifi CJK, che di caratteri alfanumerici contano come
            # lettere e finivano dritti in bocca al sintetizzatore.
            text = italian_only(text)
            # **Lettere, non alfanumerici.** Una riga letta `'11'` di caratteri
            # alfanumerici ne ha due e di lingua nessuna: passava la soglia,
            # riceveva una voce e veniva detta. Le cifre nella ROI vengono dai
            # numeri civici, dai cartelli e dai cordoli, cioe' dalla scena — una
            # battuta di soli numeri non esiste, mentre una riga di soli numeri
            # entra nell'inquadratura di continuo. Misurato dal vivo: `'11'`,
            # `"Tr'"` e `'er-s.'` sono passate tutte e tre in centocinquanta
            # secondi, e due hanno preso la voce del secondo personaggio.
            if self._lex:
                # Prima si riattaccano le parole che l'OCR ha incollato, poi si
                # conta: `'Vabene..'` non e' una parola italiana, `'va bene'`
                # sono due. Contare prima di separare boccerebbe la riga per un
                # difetto che si sa gia' riparare.
                text = self._lex.scolla(text)
            if sum(ch.isalpha() for ch in text) < max(1, self.cfg.min_ocr_chars):
                # Vuoto, o troppo corto per essere una battuta. Conta come
                # vuoto: il numero serve a vedere quanta scena sta entrando
                # nella ROI, ed e' il sintomo che una soglia va rifatta.
                self._n_empty.inc()
                continue
            if self._lex and self._lex.conta(text) == 0:
                # Nessuna parola italiana: e' la scena, non una battuta. E'
                # l'unico filtro che puo' scartare del dialogo vero — una forma
                # che i dizionari non elencano, misurata a circa una su trenta —
                # quindi si conta a parte da `empty`, che sono le righe senza
                # testo. Confonderli renderebbe impossibile vedere quale dei due
                # sta crescendo.
                self._n_gergo.inc()
                continue
            lines.append(
                OcrLine(
                    text=text,
                    cls=band.cls,
                    bbox=band.bbox,
                    luma=band.luma,
                    sat=band.sat,
                    conf=conf,
                )
            )

        candidates = merge_lines(lines, t_on=now)
        if self.tap is not None:
            self.tap(now, candidates, False)
        return self._emit(self.tracker.feed(candidates, now))

    def close(self) -> TrackerOutput:
        """Chiude le battute ancora aperte. A fine sessione o fine replay."""
        out = TrackerOutput(closed=self.tracker.close_all(self.clock.now()))
        self._n_closed.inc(len(out.closed))
        return out

    def _emit(self, out: TrackerOutput) -> TrackerOutput:
        self._n_opened.inc(len(out.opened))
        self._n_closed.inc(len(out.closed))
        return out
