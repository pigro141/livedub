"""Banco di prova: fa girare la pipeline senza gioco e senza hardware.

E' l'infrastruttura che rende possibile iterare. Un doppiaggio live e' difficile
da giudicare mentre si gioca — l'impressione conta piu' dei fatti, e le
condizioni non si ripetono mai due volte uguali. Qui invece la sorgente e' un
file, l'orologio e' virtuale, e due esecuzioni sullo stesso ingresso devono
produrre **esattamente** la stessa sequenza di eventi. Senza questa proprieta'
un confronto prima/dopo una modifica non significa niente.

    python -m tools.replay --demo --seconds 20
    python -m tools.replay --demo --determinism
    python -m tools.replay gameplay.mp4          # da F1, quando ci sara' il video

Stato F0: la sorgente sintetica e l'impalcatura di misura funzionano; la catena
montata sopra e' fatta di stadi finti, perche' quelli veri (OCR, VAD, TTS)
arrivano nelle fasi successive. Serve gia' cosi': verifica che orologio, stadi,
metriche e determinismo reggano prima che ci sia qualcosa di vero da misurare.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator, Protocol

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import VirtualClock, set_clock  # noqa: E402
from core.config import Config  # noqa: E402
from core.metrics import MetricsRegistry  # noqa: E402
from core.ring import RingBuffer  # noqa: E402
from core.stage import Chain, FnStage  # noqa: E402
from core.types import LineClass, OcrLine, merge_lines  # noqa: E402


@dataclass(slots=True)
class Packet:
    """Un istante della sorgente: un frame video, un blocco audio, o entrambi."""

    t: float
    frame: np.ndarray | None = None
    audio: np.ndarray | None = None


class Source(Protocol):
    fps: float
    samplerate: int

    def packets(self) -> Iterator[Packet]:
        ...


@dataclass
class SyntheticSource:
    """Sorgente finta ma deterministica.

    Disegna sottotitoli sintetici nella ROI secondo la grammatica reale (righe
    bianche, righe grigie, righe colorate da scartare) e produce un audio con
    raffiche di parlato finto. Non e' un gioco, ma esercita esattamente le
    strade che il video vero esercitera'.
    """

    seconds: float = 10.0
    fps: float = 30.0
    samplerate: int = 48000
    size: tuple[int, int] = (180, 640)  # altezza, larghezza della ROI
    seed: int = 0
    subtitle_every: float = 2.5
    subtitle_hold: float = 1.8

    def packets(self) -> Iterator[Packet]:
        rng = np.random.default_rng(self.seed)
        h, w = self.size
        n_frames = int(self.seconds * self.fps)
        spf = 1.0 / self.fps
        samples_per_frame = int(round(self.samplerate * spf))

        for i in range(n_frames):
            t = i * spf
            phase = t % self.subtitle_every
            visible = phase < self.subtitle_hold
            frame = np.zeros((h, w, 3), dtype=np.uint8)
            if visible:
                cycle = int(t // self.subtitle_every)
                _draw_line(frame, row=40, luma=235, text_width=int(w * 0.6))
                if cycle % 3 == 1:  # ogni tanto un secondo speaker in grigio
                    _draw_line(frame, row=80, luma=150, text_width=int(w * 0.4))
                if cycle % 4 == 3:  # ogni tanto un suggerimento colorato
                    _draw_line(frame, row=120, luma=210, text_width=int(w * 0.3), hue=(240, 200, 40))

            # Audio: raffica di parlato finto mentre il sottotitolo e' a schermo.
            base = np.zeros(samples_per_frame, dtype=np.float32)
            if visible:
                tt = np.arange(samples_per_frame, dtype=np.float32) / self.samplerate + t
                f0 = 110.0 + 40.0 * ((int(t // self.subtitle_every)) % 3)
                base = (0.25 * np.sin(2 * np.pi * f0 * tt)).astype(np.float32)
                base += (0.02 * rng.standard_normal(samples_per_frame)).astype(np.float32)
            yield Packet(t=t, frame=frame, audio=base)


def _draw_line(frame: np.ndarray, row: int, luma: int, text_width: int, hue=None) -> None:
    """Disegna una barra che imita una riga di testo. Non serve che assomigli a
    delle lettere: serve che abbia la luminanza e la saturazione giuste."""
    h, w, _ = frame.shape
    x0 = (w - text_width) // 2
    colour = np.array(hue if hue is not None else (luma, luma, luma), dtype=np.uint8)
    frame[row : row + 16, x0 : x0 + text_width] = colour


@dataclass
class ReplayStats:
    packets: int = 0
    frames: int = 0
    audio_frames: int = 0
    events: list[tuple[float, str, str]] = field(default_factory=list)
    wall_seconds: float = 0.0
    media_seconds: float = 0.0

    @property
    def speedup(self) -> float:
        return self.media_seconds / self.wall_seconds if self.wall_seconds > 0 else 0.0

    def fingerprint(self) -> str:
        """Riassunto stabile della corsa: se cambia, e' cambiato il comportamento."""
        parts = [f"{t:.4f}|{cls}|{text}" for t, cls, text in self.events]
        return f"{len(self.events)}#" + "/".join(parts)


class Replay:
    """Esecutore. Pilota un `VirtualClock` sui timestamp della sorgente."""

    def __init__(self, source: Source, cfg: Config | None = None) -> None:
        self.source = source
        self.cfg = cfg or Config()
        self.metrics = MetricsRegistry()
        self.clock = VirtualClock()
        self.ring = RingBuffer(
            capacity=int(self.cfg.audio.ring_seconds * source.samplerate),
            channels=1,
            samplerate=source.samplerate,
        )
        self.chain = self._build_chain()

    def _build_chain(self) -> Chain:
        """Catena F0: stadi finti al posto di OCR/VAD/TTS.

        Il classificatore di righe qui e' *vero* — legge luminanza e saturazione
        come fara' quello definitivo — mentre il riconoscimento dei caratteri e'
        sostituito da un testo segnaposto: in F0 non c'e' ancora un OCR, e
        fingere di averlo nasconderebbe cosa e' gia' verificato e cosa no.
        """
        return Chain(
            "video",
            [
                FnStage("vision.classify", self._classify, metrics=self.metrics, clock=self.clock),
                FnStage("vision.merge", self._merge, metrics=self.metrics, clock=self.clock),
            ],
            metrics=self.metrics,
            clock=self.clock,
        )

    def _classify(self, frame: np.ndarray | None) -> list[OcrLine]:
        """Trova le righe nella ROI e le classifica per colore.

        Anticipa in piccolo la logica di `vision/`: proiezione orizzontale per
        trovare le bande di testo, poi saturazione (scarta) e luminanza
        (bianco/grigio).
        """
        if frame is None:
            return []
        vis = self.cfg.vision
        rgb = frame.astype(np.int16)
        luma = rgb.mean(axis=2)
        sat = rgb.max(axis=2) - rgb.min(axis=2)
        rows = np.where((luma > vis.grey_min_luma).sum(axis=1) > 0)[0]
        if rows.size == 0:
            return []

        lines: list[OcrLine] = []
        for top, bottom in _bands(rows, min_height=vis.min_line_height):
            band_luma = luma[top : bottom + 1]
            band_sat = sat[top : bottom + 1]
            mask = band_luma > vis.grey_min_luma
            if not mask.any():
                continue
            max_sat = float(band_sat[mask].max())
            med_luma = float(np.median(band_luma[mask]))
            if max_sat > vis.sat_max:
                cls = LineClass.COLORED
            elif med_luma >= vis.white_min_luma:
                cls = LineClass.WHITE
            else:
                cls = LineClass.GREY
            lines.append(
                OcrLine(
                    text=f"[{cls.value}]",  # segnaposto: l'OCR vero arriva in F1
                    cls=cls,
                    bbox=(0, int(top), int(frame.shape[1]), int(bottom - top + 1)),
                    luma=med_luma,
                    sat=max_sat,
                )
            )
        return lines

    def _merge(self, lines: list[OcrLine]):
        return merge_lines(lines, t_on=self.clock.now())

    def run(self, quiet: bool = False) -> ReplayStats:
        import time

        stats = ReplayStats()
        previous = set_clock(self.clock)
        wall0 = time.perf_counter()
        last_text: str | None = None
        try:
            for packet in self.source.packets():
                self.clock.set(packet.t)
                stats.packets += 1
                if packet.audio is not None:
                    self.ring.write(packet.audio)
                    stats.audio_frames += len(packet.audio)
                if packet.frame is not None:
                    stats.frames += 1
                    events = self.chain.run(packet.frame)
                    # Solo i cambi contano: un sottotitolo fermo per 50 frame e'
                    # una battuta sola, non cinquanta.
                    signature = "|".join(f"{e.cls.value}:{e.text}" for e in events)
                    if signature != last_text:
                        last_text = signature
                        for e in events:
                            stats.events.append((e.t_on, e.cls.value, e.text))
                stats.media_seconds = packet.t
        finally:
            set_clock(previous)
        stats.wall_seconds = time.perf_counter() - wall0
        if not quiet:
            self._report(stats)
        return stats

    def _report(self, stats: ReplayStats) -> None:
        print(
            f"replay: {stats.frames} frame, {stats.media_seconds:.1f}s di media "
            f"in {stats.wall_seconds:.2f}s ({stats.speedup:.0f}x tempo reale)"
        )
        print(f"battute rilevate: {len(stats.events)}")
        print()
        print(self.metrics.report())


def _bands(rows: np.ndarray, min_height: int) -> list[tuple[int, int]]:
    """Raggruppa indici di riga contigui in bande, scartando quelle troppo
    sottili per essere testo."""
    if rows.size == 0:
        return []
    out: list[tuple[int, int]] = []
    start = prev = int(rows[0])
    for r in rows[1:]:
        r = int(r)
        if r == prev + 1:
            prev = r
            continue
        if prev - start + 1 >= min_height:
            out.append((start, prev))
        start = prev = r
    if prev - start + 1 >= min_height:
        out.append((start, prev))
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tools.replay", description="Fa girare la pipeline da file, senza gioco."
    )
    ap.add_argument("video", nargs="?", help="registrazione da riprodurre (da F1)")
    ap.add_argument("--demo", action="store_true", help="usa la sorgente sintetica")
    ap.add_argument("--seconds", type=float, default=10.0, help="durata della sorgente sintetica")
    ap.add_argument("--seed", type=int, default=0, help="seme della sorgente sintetica")
    ap.add_argument(
        "--determinism",
        action="store_true",
        help="esegue due volte e verifica che gli eventi coincidano",
    )
    ap.add_argument("--set", action="append", dest="overrides", metavar="CHIAVE=VALORE")
    args = ap.parse_args(argv)

    if args.video and not args.demo:
        print("Il decoder video arriva in F1: per ora usa --demo.", file=sys.stderr)
        return 2
    if not args.video and not args.demo:
        ap.print_help()
        return 2

    cfg = Config().apply(args.overrides)

    def once(quiet: bool) -> ReplayStats:
        source = SyntheticSource(seconds=args.seconds, seed=args.seed)
        return Replay(source, cfg).run(quiet=quiet)

    if args.determinism:
        a = once(quiet=True)
        b = once(quiet=True)
        same = a.fingerprint() == b.fingerprint()
        print(f"corsa A: {len(a.events)} battute\ncorsa B: {len(b.events)} battute")
        print("determinismo: OK" if same else "determinismo: VIOLATO — le due corse differiscono")
        return 0 if same else 1

    once(quiet=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
