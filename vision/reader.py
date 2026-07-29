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
        )
        self.tracker = SubtitleTracker(cfg)
        self._recheck = 0

        m = self.metrics
        self._t_diff = m.timer("vision.diff")
        self._t_classify = m.timer("vision.classify")
        self._t_ocr = m.timer("vision.ocr")
        self._n_ocr = m.counter("vision.ocr.lines")
        self._n_colored = m.counter("vision.lines.colored")
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
        self._recheck -= 1

        t0 = time.perf_counter()
        bands = classify_lines(roi, self.cfg)
        self._t_classify.add((time.perf_counter() - t0) * 1000.0)

        lines: list[OcrLine] = []
        for band in bands:
            if not band.cls.is_dialogue:
                # Scartata dal colore, prima di pagare il riconoscimento.
                self._n_colored.inc()
                continue
            t0 = time.perf_counter()
            text, conf = self.ocr.read(band.crop)
            self._t_ocr.add((time.perf_counter() - t0) * 1000.0)
            self._n_ocr.inc()
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
