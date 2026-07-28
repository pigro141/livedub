"""Banco di prova: fa girare la pipeline senza gioco e senza hardware.

E' l'infrastruttura che rende possibile iterare. Un doppiaggio live e' difficile
da giudicare mentre si gioca — l'impressione conta piu' dei fatti, e le
condizioni non si ripetono mai due volte uguali. Qui invece la sorgente e' un
file, l'orologio e' virtuale, e due esecuzioni sullo stesso ingresso devono
produrre **esattamente** la stessa sequenza di eventi. Senza questa proprieta'
un confronto prima/dopo una modifica non significa niente.

    python -m tools.replay --demo --seconds 20
    python -m tools.replay --demo --determinism
    python -m tools.replay gameplay.mp4 --start 60 --end 180
    python -m tools.replay gameplay.mp4 --peek 8      # ritagli della ROI su PNG

Due catene, e la differenza conta:

- **`--demo`** monta stadi finti su una sorgente disegnata. Il classificatore di
  righe e' vero, il riconoscimento e' un segnaposto. Serve a verificare che
  orologio, stadi, metriche e determinismo reggano;
- **su un video** monta il `SubtitleReader` vero, cioe' il dominio video di F1
  per intero, OCR compreso. E' la catena che produce le durate su cui si tara
  il tempo di F2, e quei numeri devono venire dal codice che gira in gioco, non
  da una sua imitazione.

`--peek` non fa girare niente: salva i ritagli della ROI cosi' come la pipeline
li vede. E' il primo passo obbligato su una registrazione nuova, perche' una ROI
sbagliata non da' errore — da' zero battute, oppure battute plausibili e false.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.clock import VirtualClock, set_clock  # noqa: E402
from core.config import Config, load_profile  # noqa: E402
from core.metrics import MetricsRegistry  # noqa: E402
from core.ring import RingBuffer  # noqa: E402
from core.stage import Chain, FnStage  # noqa: E402
from core.types import LineClass, OcrLine, SubtitleEvent, merge_lines  # noqa: E402
from tools.reads import Recorder  # noqa: E402
from tools.sources import Packet, Source, SyntheticSource, VideoSource, probe  # noqa: E402,F401
from vision.roi import crop  # noqa: E402
from vision.subtitles import TrackerOutput  # noqa: E402


@dataclass
class ReplayStats:
    packets: int = 0
    frames: int = 0
    audio_frames: int = 0
    events: list[tuple[float, str, str]] = field(default_factory=list)
    closed: list[SubtitleEvent] = field(default_factory=list)
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

    def __init__(
        self,
        source: Source,
        cfg: Config | None = None,
        *,
        real: bool = False,
        tap=None,
    ) -> None:
        self.source = source
        self.cfg = cfg or Config()
        self.real = real
        self.tap = tap
        self.metrics = MetricsRegistry()
        self.clock = VirtualClock()
        self.ring = RingBuffer(
            capacity=int(self.cfg.audio.ring_seconds * source.samplerate),
            channels=1,
            samplerate=source.samplerate,
        )
        self.reader = None
        self.chain = self._build_real_chain() if real else self._build_fake_chain()

    # -- le due catene -----------------------------------------------------

    def _build_real_chain(self) -> Chain:
        """Il dominio video di F1 per intero: diff, righe, OCR, stabilizzatore."""
        from vision.ocr import make_ocr
        from vision.reader import SubtitleReader

        self.reader = SubtitleReader(
            self.cfg.vision,
            make_ocr(self.cfg.vision.ocr_backend, self.cfg.vision.ocr_device),
            metrics=self.metrics,
            clock=self.clock,
            tap=self.tap,
            # Sul banco un errore deve gridare: e' il posto dove si vuole
            # sapere che l'OCR e' caduto, non dove si vuole sopravvivere.
            on_error="raise",
        )
        return Chain("video", [self.reader], metrics=self.metrics, clock=self.clock)

    def _build_fake_chain(self) -> Chain:
        """Catena F0: stadi finti al posto di OCR/VAD/TTS.

        Il classificatore di righe qui e' *vero* — legge luminanza e saturazione
        come fara' quello definitivo — mentre il riconoscimento dei caratteri e'
        sostituito da un testo segnaposto: fingere di avere un OCR
        nasconderebbe cosa e' gia' verificato e cosa no.
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
                    text=f"[{cls.value}]",  # segnaposto: l'OCR vero sta nella catena reale
                    cls=cls,
                    bbox=(0, int(top), int(frame.shape[1]), int(bottom - top + 1)),
                    luma=med_luma,
                    sat=max_sat,
                )
            )
        return lines

    def _merge(self, lines: list[OcrLine]):
        return merge_lines(lines, t_on=self.clock.now())

    # -- esecuzione --------------------------------------------------------

    def run(self, quiet: bool = False, on_event=None) -> ReplayStats:
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
                    result = self.chain.run(packet.frame)
                    if isinstance(result, TrackerOutput):
                        stats.closed.extend(result.closed)
                        for e in result.opened:
                            stats.events.append((e.t_on, e.cls.value, e.text))
                            if on_event is not None:
                                on_event(e)
                    else:
                        # Catena finta: gli eventi si ripetono a ogni frame,
                        # solo i cambi contano. Un sottotitolo fermo per 50
                        # frame e' una battuta sola, non cinquanta.
                        signature = "|".join(f"{e.cls.value}:{e.text}" for e in result)
                        if signature != last_text:
                            last_text = signature
                            for e in result:
                                stats.events.append((e.t_on, e.cls.value, e.text))
                                if on_event is not None:
                                    on_event(e)
                stats.media_seconds = packet.t
        finally:
            if self.reader is not None:
                # Senza questa chiusura l'ultima battuta resta senza durata, e
                # sparisce proprio dalla misura che la cerca.
                stats.closed.extend(self.reader.close().closed)
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
        print(f"battute rilevate: {len(stats.events)}  chiuse: {len(stats.closed)}")
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


# -- sguardo alla ROI ------------------------------------------------------


def peek(video: str, cfg: Config, n: int, out_dir: Path, start: float, end: float | None) -> int:
    """Salva `n` ritagli della ROI presi a intervalli regolari.

    Prima misura da fare su una registrazione nuova, e non e' una misura: e' un
    controllo che la misura *possa* dire qualcosa. Se la ROI e' fuori posto
    l'OCR restituisce zero battute e il grafico dei residui esce vuoto, che
    somiglia moltissimo a "il modello lineare non regge".
    """
    import cv2

    info = probe(video)
    print(info)
    t_end = end if end is not None else info.duration
    if t_end <= start:
        print(f"intervallo vuoto: {start} .. {t_end}", file=sys.stderr)
        return 2

    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(info.path))
    try:
        for i in range(n):
            t = start + (t_end - start) * (i + 0.5) / n
            cap.set(cv2.CAP_PROP_POS_FRAMES, int(round(t * info.src_fps)))
            ok, frame = cap.read()
            if not ok:
                print(f"  t={t:7.1f}s  lettura fallita", file=sys.stderr)
                continue
            roi = crop(frame, cfg.vision.roi)
            path = out_dir / f"roi_{i:02d}_t{t:07.1f}.png"
            cv2.imwrite(str(path), roi)
            full = out_dir / f"full_{i:02d}_t{t:07.1f}.jpg"
            cv2.imwrite(str(full), cv2.resize(frame, (frame.shape[1] // 2, frame.shape[0] // 2)))
            print(f"  t={t:7.1f}s  -> {path.name}  ({roi.shape[1]}x{roi.shape[0]})")
    finally:
        cap.release()
    print(f"\nROI normalizzata: {cfg.vision.roi}")
    print(f"-> {out_dir}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tools.replay", description="Fa girare la pipeline da file, senza gioco."
    )
    ap.add_argument("video", nargs="?", help="registrazione da riprodurre")
    ap.add_argument("--demo", action="store_true", help="usa la sorgente sintetica")
    ap.add_argument("--seconds", type=float, default=10.0, help="durata della sorgente sintetica")
    ap.add_argument("--seed", type=int, default=0, help="seme della sorgente sintetica")
    ap.add_argument("--start", type=float, default=0.0, help="secondo di inizio nel video")
    ap.add_argument("--end", type=float, default=None, help="secondo di fine nel video")
    ap.add_argument("--fps", type=float, default=None, help="ritmo di campionamento dei frame")
    ap.add_argument("--peek", type=int, metavar="N", help="salva N ritagli della ROI e basta")
    ap.add_argument(
        "--dump-reads",
        metavar="FILE",
        help="registra ogni alimentazione del tracker su JSONL (vedi tools.retrack)",
    )
    ap.add_argument("--out", default="runs/peek", help="cartella per i ritagli di --peek")
    ap.add_argument(
        "--determinism",
        action="store_true",
        help="esegue due volte e verifica che gli eventi coincidano",
    )
    ap.add_argument(
        "--profile",
        default=None,
        help="profilo del gioco (profiles/<nome>.json). Senza, si usano i default.",
    )
    ap.add_argument("--set", action="append", dest="overrides", metavar="CHIAVE=VALORE")
    args = ap.parse_args(argv)

    if not args.video and not args.demo:
        ap.print_help()
        return 2

    # Il sintetico gira sui default apposta: la sorgente disegnata usa i colori
    # dei default, e caricarci sopra un profilo calibrato su un gioco vero
    # renderebbe il banco muto senza dire perche'.
    cfg = load_profile(args.profile, args.overrides) if args.profile else Config().apply(args.overrides)
    fps = args.fps if args.fps is not None else cfg.capture.fps

    if args.video and args.peek:
        return peek(args.video, cfg, args.peek, Path(args.out), args.start, args.end)

    def once(quiet: bool) -> ReplayStats:
        if args.video:
            source = VideoSource(args.video, fps=fps, start=args.start, end=args.end)
            if not quiet:
                print(source.info)
                print(f"campionamento: 1 frame ogni {source.step} -> {source.fps:.2f} fps\n")
            recorder = Recorder(args.dump_reads) if args.dump_reads else None
            stats = Replay(source, cfg, real=True, tap=recorder).run(quiet=quiet)
            if recorder is not None:
                path = recorder.write()
                if not quiet:
                    print(f"\nletture registrate: {len(recorder.records)} -> {path}")
            return stats
        source = SyntheticSource(seconds=args.seconds, seed=args.seed)
        return Replay(source, cfg, real=False).run(quiet=quiet)

    if args.determinism:
        a = once(quiet=True)
        b = once(quiet=True)
        same = a.fingerprint() == b.fingerprint()
        print(f"corsa A: {len(a.events)} battute\ncorsa B: {len(b.events)} battute")
        print("determinismo: OK" if same else "determinismo: VIOLATO — le due corse differiscono")
        return 0 if same else 1

    stats = once(quiet=False)
    if args.video and stats.events:
        print("\nbattute lette:")
        for t, cls, text in stats.events[:40]:
            print(f"  t={t:7.2f}s [{cls:6}] {text[:70]!r}")
        if len(stats.events) > 40:
            print(f"  ... e altre {len(stats.events) - 40}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
