"""Quanto costa la catena video **dal vivo**, mentre il gioco gira.

    python -m tools.bench_capture --seconds 30 --profile gtav
    python -m tools.bench_capture --seconds 30 --peek 6      # guarda la ROI

E' l'unica misura che il banco da file non puo' fare, e riguarda l'assunzione su
cui poggia tutto il prodotto: che cattura, classificazione e OCR stiano dentro
il budget mentre la GPU e la CPU sono occupate da un gioco.

Da file il frame e' gia' in memoria e la macchina non fa altro. Qui il frame va
strappato alla scheda video, e ogni millisecondo e' conteso.

**Cosa salva su disco**: solo i ritagli della ROI con `--peek`, cioe' la striscia
dei sottotitoli, e solo se lo si chiede. Mai lo schermo intero: la misura non ne
ha bisogno e un banco che archivia il desktop di chi lo esegue e' un banco che
si usa una volta sola.

**Cosa misura, e in che ordine di importanza:**

1. il costo a muro dei tre stadi, separati — se il totale sfonda il budget si
   deve sapere *chi* lo sfonda, e la risposta cambia il rimedio;
2. la latenza da frame a testo, che e' quella che l'utente sente;
3. il ritmo effettivo: quanti frame si riesce davvero a servire al secondo, che
   e' diverso dal costo medio perche' include tutto cio' che sta in mezzo.

Il diff resta il cancello: quando lo schermo non cambia l'OCR non gira, quindi
il costo *tipico* e quello del *caso peggiore* sono due numeri diversi e vanno
letti separati. Un p50 basso con un p99 fuori budget non e' un buon risultato:
significa che la catena regge tranne quando serve.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capture.screen import make_screen  # noqa: E402
from core.clock import RealClock, set_clock  # noqa: E402
from core.config import Config, load_profile  # noqa: E402
from core.metrics import MetricsRegistry  # noqa: E402
from vision.ocr import make_ocr  # noqa: E402
from vision.reader import SubtitleReader  # noqa: E402
from vision.roi import crop  # noqa: E402


def percentili(v: list[float]) -> str:
    if not v:
        return "nessun campione"
    a = np.asarray(v)
    return (
        f"p50 {np.percentile(a,50):6.2f}  p90 {np.percentile(a,90):7.2f}  "
        f"p99 {np.percentile(a,99):7.2f}  max {a.max():7.2f} ms   (n={len(a)})"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tools.bench_capture",
        description="Costo della catena video dal vivo, mentre il gioco gira.",
    )
    ap.add_argument("--seconds", type=float, default=20.0, help="durata della prova")
    ap.add_argument("--profile", default=None, help="profilo del gioco")
    ap.add_argument("--backend", default="auto", help="auto | dxcam | mss")
    ap.add_argument("--monitor", type=int, default=1, help="monitor (1 = principale)")
    ap.add_argument("--set", action="append", dest="overrides", metavar="CHIAVE=VALORE")
    ap.add_argument("--peek", type=int, default=0, metavar="N", help="salva N ritagli della ROI")
    ap.add_argument("--out", default="runs/peek_live", help="cartella per i ritagli")
    ap.add_argument("--no-ocr", action="store_true", help="solo cattura, per isolarne il costo")
    ap.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="secondi di attesa prima di cominciare: il tempo di portare il gioco davanti",
    )
    args = ap.parse_args(argv)

    cfg = load_profile(args.profile, args.overrides) if args.profile else Config().apply(args.overrides)
    set_clock(RealClock())
    metrics = MetricsRegistry()

    screen = make_screen(args.backend, monitor=args.monitor)
    if screen.name != "dxcam" and args.backend in ("auto", "dxcam"):
        print(f"! Desktop Duplication non disponibile, si misura {screen.name} (piu' lento)")
    print(f"cattura: {screen.name}   monitor {args.monitor}   profilo {args.profile or '(default)'}")

    reader = None
    if not args.no_ocr:
        reader = SubtitleReader(
            cfg.vision,
            make_ocr(cfg.vision.ocr_backend, cfg.vision.ocr_device),
            metrics=metrics,
            on_error="raise",
        )
        print(f"OCR: {cfg.vision.ocr_backend} su {cfg.vision.ocr_device}")

    peek_dir = Path(args.out)
    if args.peek:
        peek_dir.mkdir(parents=True, exist_ok=True)

    if args.delay > 0:
        # Con un monitor solo, chi lancia la prova ha la finestra del terminale
        # davanti al gioco: senza questa attesa si misura la cattura della
        # console, che e' una misura perfettamente riuscita della cosa sbagliata.
        print(f"\n>>> {args.delay:.0f} secondi per portare il gioco in primo piano...")
        time.sleep(args.delay)
        print(">>> via\n")

    t_grab, t_full, salti = [], [], 0
    battute, ultimo_peek, n_peek = [], 0.0, 0
    forma = None
    periodo = 1.0 / max(1e-6, cfg.capture.fps)
    t_start = time.perf_counter()
    prossimo = t_start

    try:
        while time.perf_counter() - t_start < args.seconds:
            ora = time.perf_counter()
            if ora < prossimo:
                time.sleep(min(0.002, prossimo - ora))
                continue
            prossimo += periodo

            g0 = time.perf_counter()
            got = screen.grab()
            g1 = time.perf_counter()
            if not got.ok:
                # Lo schermo non e' cambiato: non e' un frame catturato a costo
                # zero, e' un frame che non c'e'. Contarlo fra le catture
                # abbasserebbe la mediana senza che nulla sia piu' veloce.
                salti += 1
                continue
            t_grab.append((g1 - g0) * 1000.0)
            forma = got.frame.shape

            if reader is not None:
                out = reader.run(got.frame)
                t_full.append((time.perf_counter() - g0) * 1000.0)
                for ev in out.opened:
                    battute.append((time.perf_counter() - t_start, ev.text))
                    print(f"  [{battute[-1][0]:6.1f}s] {ev.text[:78]!r}")
            else:
                t_full.append((g1 - g0) * 1000.0)

            if args.peek and n_peek < args.peek and (time.perf_counter() - ultimo_peek) > (
                args.seconds / max(1, args.peek)
            ):
                import cv2

                roi = crop(got.frame, cfg.vision.roi)
                cv2.imwrite(str(peek_dir / f"live_{n_peek:02d}.png"), roi)
                n_peek += 1
                ultimo_peek = time.perf_counter()
    except KeyboardInterrupt:
        print("\ninterrotto")
    finally:
        screen.close()

    durata = time.perf_counter() - t_start
    print(f"\nschermo: {forma}   {len(t_grab)} frame in {durata:.1f}s "
          f"= {len(t_grab)/max(1e-9,durata):.1f} fps   (chiesti {cfg.capture.fps:.0f})")
    print(f"frame non cambiati (nessuna cattura): {salti}")
    print(f"\ncattura        {percentili(t_grab)}")
    if reader is not None:
        print(f"cattura+lettura{percentili(t_full)}")
        print()
        print(metrics.report())
        print(f"\nbattute lette: {len(battute)}")
    if args.peek:
        print(f"ritagli della ROI -> {peek_dir}  (solo la striscia dei sottotitoli)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
