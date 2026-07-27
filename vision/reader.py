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
"""

from __future__ import annotations

import time

import numpy as np

from core.clock import Clock
from core.config import VisionConfig
from core.metrics import MetricsRegistry
from core.stage import Stage
from core.types import OcrLine, merge_lines
from vision.diff import Change, RoiDiff
from vision.lines import classify_lines
from vision.ocr import NullOcr, OcrBackend
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
        **kw,
    ) -> None:
        super().__init__("vision.read", metrics=metrics, clock=clock, **kw)
        self.cfg = cfg
        self.ocr = ocr if ocr is not None else NullOcr()
        self.diff = RoiDiff(
            threshold=cfg.diff_threshold,
            stride=cfg.diff_stride,
            ink_min_luma=cfg.grey_min_luma,
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
            if not text.strip():
                self._n_empty.inc()
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

        return self._emit(self.tracker.feed(merge_lines(lines, t_on=now), now))

    def close(self) -> TrackerOutput:
        """Chiude le battute ancora aperte. A fine sessione o fine replay."""
        out = TrackerOutput(closed=self.tracker.close_all(self.clock.now()))
        self._n_closed.inc(len(out.closed))
        return out

    def _emit(self, out: TrackerOutput) -> TrackerOutput:
        self._n_opened.inc(len(out.opened))
        self._n_closed.inc(len(out.closed))
        return out
