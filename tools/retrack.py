"""Banco dello stabilizzatore: stesse letture, tracker diverso.

    python -m tools.replay video.mp4 --profile gtav --start 1240 --end 1290 \
        --dump-reads runs\\reads.jsonl          # una volta, ~55 s di OCR
    python -m tools.retrack runs\\reads.jsonl   # tutte le altre, ~50 ms

Serve a tarare `vision/subtitles.py` senza ri-pagare l'OCR e — piu' importante —
**a parita' esatta di ingresso**: due tarature confrontate su due esecuzioni
diverse del video sarebbero confrontate anche su tutto il rumore che le separa.

## Come si misura la frammentazione senza girare in tondo

Il difetto da sciogliere e' che la stessa battuta viene riaperta piu' volte
perche' due sue letture non si somigliano abbastanza. La tentazione e' contare
le battute "davvero distinte" raggruppandole per somiglianza — ma la somiglianza
e' esattamente il parametro in taratura, e la misura direbbe sempre che il
valore corrente e' quello giusto.

Serve un indicatore indipendente, e sono le **durate**. Un sottotitolo di gioco
sta a schermo per secondi; una battuta riaperta quattro volte produce quattro
frammenti brevi al posto di uno lungo. Quindi:

- `aperture` scende quando la frammentazione si scioglie;
- `frammenti` (durata sotto `--short`, di suo 0,6 s) e' il sintomo diretto, e
  non consulta il testo;
- `copertura` (somma delle durate / arco di tempo osservato) e' la guardia
  contro il rimedio peggiore del male: alzare la soglia finche' due battute
  diverse si fondono fa scendere le aperture e **sale** la copertura oltre il
  ragionevole, perche' una battuta sola si prende il posto di due.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config, load_profile  # noqa: E402
from core.types import SubtitleEvent  # noqa: E402
from tools.reads import load  # noqa: E402
from vision.subtitles import SubtitleTracker  # noqa: E402


def retrack(feeds: list[tuple[float, list[SubtitleEvent], bool]], cfg) -> list[SubtitleEvent]:
    """Rifa' girare il solo stabilizzatore sul flusso registrato.

    Restituisce le battute **chiuse**, cioe' quelle con una durata: sono l'unica
    forma in cui una battuta e' utile alla calibrazione del tempo.
    """
    tracker = SubtitleTracker(cfg)
    closed: list[SubtitleEvent] = []
    t = 0.0
    for t, candidates, certain in feeds:
        out = tracker.feed(candidates, t, certain=certain)
        closed.extend(out.closed)
    closed.extend(tracker.close_all(t))
    return sorted(closed, key=lambda e: e.t_on)


def percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def report(closed: list[SubtitleEvent], span: float, short: float, show: int) -> dict:
    durations = [e.duration for e in closed if e.duration is not None]
    fragments = [d for d in durations if d < short]
    stats = {
        "aperture": len(closed),
        "frammenti": len(fragments),
        "p10": percentile(durations, 0.10),
        "p50": percentile(durations, 0.50),
        "p90": percentile(durations, 0.90),
        "copertura": sum(durations) / span if span > 0 else 0.0,
    }
    print(
        f"aperture {stats['aperture']}   frammenti <{short:.1f}s {stats['frammenti']}   "
        f"durata p10/p50/p90 {stats['p10']:.2f}/{stats['p50']:.2f}/{stats['p90']:.2f}s   "
        f"copertura {stats['copertura']:.2f}"
    )
    if show:
        print()
        for e in closed[:show]:
            d = e.duration if e.duration is not None else float("nan")
            mark = "  <-- frammento" if d < short else ""
            print(f"  t={e.t_on:8.2f}s  d={d:5.2f}s [{e.cls.value:6}] {e.text[:64]!r}{mark}")
        if len(closed) > show:
            print(f"  ... e altre {len(closed) - show}")
    return stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tools.retrack",
        description="Rifa' girare lo stabilizzatore su letture gia' registrate.",
    )
    ap.add_argument("reads", help="JSONL prodotto da tools.replay --dump-reads")
    ap.add_argument("--profile", default=None, help="profilo del gioco")
    ap.add_argument("--set", action="append", dest="overrides", metavar="CHIAVE=VALORE")
    ap.add_argument("--short", type=float, default=0.6, help="sotto questa durata e' un frammento")
    ap.add_argument("--show", type=int, default=60, help="quante battute elencare (0 = nessuna)")
    ap.add_argument(
        "--raw",
        nargs=2,
        type=float,
        metavar=("DA", "A"),
        help="elenca le alimentazioni grezze in questo intervallo e basta",
    )
    args = ap.parse_args(argv)

    cfg = load_profile(args.profile, args.overrides) if args.profile else Config().apply(args.overrides)
    feeds = load(args.reads)
    if not feeds:
        print(f"nessuna lettura in {args.reads}", file=sys.stderr)
        return 2
    span = feeds[-1][0] - feeds[0][0]
    print(f"{len(feeds)} alimentazioni su {span:.1f}s di media\n")

    if args.raw:
        # Ogni lettura, non solo quelle che arrivano in fondo. Una battuta
        # riaperta si spiega quasi sempre qui e quasi mai nell'uscita.
        lo, hi = args.raw
        for t, candidates, certain in feeds:
            if not lo <= t <= hi:
                continue
            mark = " CERTAIN" if certain else ""
            if not candidates:
                print(f"  t={t:8.2f}s{mark}  (nessuna candidata)")
            for ev in candidates:
                print(f"  t={t:8.2f}s{mark}  [{ev.cls.value:6}] {ev.text!r}")
        return 0
    closed = retrack(feeds, cfg.vision)
    report(closed, span, args.short, args.show)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
