"""Quanto resta a schermo una battuta, e quanto lo si puo' prevedere.

    python -m tools.bench_timing runs\\reads_full.jsonl --profile gtav
    python -m tools.bench_timing gameplay.mp4 --profile gtav      # ripaga l'OCR

E' la misura su cui poggia tutta F2. Il sottotitolo compare a `T` e la sua
durata `D` si conosce solo quando sparisce, cioe' troppo tardi per servire:
bisogna prevederla dal testo, con `D = a + b * n_caratteri`. Quei due
coefficienti non si indovinano, e finche' non sono misurati la pipeline sta
usando due numeri dichiarati.

**Il numero che conta non e' `a` e non e' `b`, sono i residui.** Una retta si
adatta a qualunque nuvola di punti e restituisce sempre due coefficienti; se la
dispersione e' di un secondo e mezzo, quei coefficienti sono precisi e inutili,
perche' l'errore tipico e' piu' grande dell'intera correzione che WSOLA puo'
fare (`rate` fra 0,85 e 1,35 su una battuta di due secondi vale circa +/-0,4 s).
Quindi il banco stampa la distribuzione dei residui e la quota di battute
prevista entro quella fascia, e la retta viene dopo.

**E prima ancora, la misura deve poter esprimere la risposta.** Due controlli
che vengono prima della regressione:

- le battute troppo corte non sono battute corte, sono *frammenti* — una battuta
  riaperta a meta' produce due durate false, e in mezzo alla nuvola pesano come
  dati veri. Si riportano entrambe le versioni, con e senza, perche' scegliere
  in silenzio quale tenere e' il modo piu' comodo di ottenere il risultato che
  si spera;
- la relazione va **guardata a fette**, non solo adattata: se la durata mediana
  per fascia di lunghezza non sale, la lunghezza non e' il predittore giusto e
  nessun `b` lo rende tale.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import Config, load_profile  # noqa: E402
from core.types import SubtitleEvent  # noqa: E402
from fuse.timing import spoken_length as letters  # noqa: E402

# La lunghezza si conta in un posto solo. Il banco che misura i coefficienti e
# il modello che li usa devono contare la **stessa** cosa: due definizioni che
# divergono di uno spazio darebbero coefficienti giusti per una lunghezza che
# nessuno calcola piu'.



def collect(path: str, cfg: Config) -> list[SubtitleEvent]:
    """Le battute chiuse, da un file di letture o dal video."""
    if path.lower().endswith(".jsonl"):
        from tools.reads import load
        from tools.retrack import retrack

        return retrack(load(path), cfg.vision)

    from tools.replay import Replay
    from tools.sources import VideoSource

    source = VideoSource(path, fps=cfg.capture.fps)
    stats = Replay(source, cfg, real=True).run(quiet=True)
    return sorted(stats.closed, key=lambda e: e.t_on)


def fit(n: np.ndarray, d: np.ndarray) -> tuple[float, float]:
    """Retta ai minimi quadrati `D = a + b*n`."""
    if len(n) < 2:
        return 0.0, 0.0
    b, a = np.polyfit(n, d, 1)
    return float(a), float(b)


def describe(name: str, n: np.ndarray, d: np.ndarray, rate_limits: tuple[float, float]) -> None:
    """Retta, residui, e quanta parte del lavoro resta a WSOLA."""
    a, b = fit(n, d)
    pred = a + b * n
    res = d - pred
    lo, hi = rate_limits

    print(f"\n== {name}: {len(d)} battute ==")
    print(f"   durata   p10 {np.percentile(d,10):5.2f}  p50 {np.percentile(d,50):5.2f}  "
          f"p90 {np.percentile(d,90):5.2f}  media {d.mean():5.2f}s")
    print(f"   retta    D = {a:.3f} + {b:.4f} * n_caratteri")
    if len(d) > 2:
        corr = float(np.corrcoef(n, d)[0, 1])
        print(f"   correlazione lunghezza/durata: {corr:+.3f}   R2 = {corr**2:.3f}")
    print(f"   residui  p10 {np.percentile(res,10):+5.2f}  p50 {np.percentile(res,50):+5.2f}  "
          f"p90 {np.percentile(res,90):+5.2f}   MAE {np.abs(res).mean():.2f}s  "
          f"RMSE {np.sqrt((res**2).mean()):.2f}s")

    # La domanda vera: l'errore sta dentro cio' che lo stiramento sa correggere?
    # Su una battuta prevista `pred`, WSOLA copre da pred/hi a pred/lo.
    coperti = ((d >= pred / hi) & (d <= pred / lo)).mean()
    print(f"   entro la fascia correggibile da WSOLA ({lo:.2f}-{hi:.2f}): {coperti:6.1%}")

    # E la stessa cosa guardata come va guardata: i due errori non si
    # equivalgono. Se la battuta dura piu' del previsto la voce finisce in
    # anticipo, e non se ne accorge nessuno. Se dura meno, la voce sfora. Una
    # misura che li somma non puo' esprimere la differenza fra un difetto e un
    # non-difetto, e per met'a di questa tabella e' stata proprio quella.
    tardi = res < 0  # durata vera piu' corta della prevista: si sfora
    print(f"   in anticipo (innocuo) {(~tardi).mean():6.1%}   "
          f"in ritardo (sfora) {tardi.mean():6.1%}, "
          f"e di quanto: p50 {np.percentile(-res[tardi], 50) if tardi.any() else 0:.2f}s  "
          f"p90 {np.percentile(-res[tardi], 90) if tardi.any() else 0:.2f}s")


def collisions(events: list[SubtitleEvent], a: float, b: float) -> None:
    """Sforare non e' il problema: **collidere con la battuta dopo** lo e'.

    Una voce che continua mentre a schermo non c'e' piu' niente non disturba
    nessuno — il sottotitolo e' sparito, il personaggio ha finito, e il
    doppiaggio arriva un attimo dopo come in un doppiaggio qualsiasi. Il difetto
    vero e' parlare sopra la battuta successiva, perche' li' due voci si
    accavallano e si perde una riga.

    Quindi la domanda giusta non e' quanto e' preciso `D`, ma se lo sforamento
    entra nel silenzio o nella battuta dopo. E' anche la ragione per cui i
    numeri qui sopra, presi da soli, dipingono la situazione peggiore di com'e'.
    """
    ordered = sorted((e for e in events if e.duration is not None), key=lambda e: e.t_on)
    sforo, buchi = [], []
    for cur, nxt in zip(ordered, ordered[1:]):
        gap = nxt.t_on - cur.t_on  # quanto tempo c'e' prima della prossima
        predetta = a + b * letters(cur.text)
        buchi.append(gap - cur.duration)
        sforo.append(predetta - gap)  # >0 = la voce invade la battuta dopo
    if not sforo:
        return
    sf = np.array(sforo)
    bu = np.array(buchi)
    print(f"\n   intervallo fino alla battuta dopo: p10 {np.percentile(bu,10):+5.2f}  "
          f"p50 {np.percentile(bu,50):+5.2f}  p90 {np.percentile(bu,90):+5.2f}s")
    print(f"   la voce invaderebbe la battuta successiva: {(sf > 0).mean():6.1%}  "
          f"(di quanto, p90: {np.percentile(sf[sf > 0], 90) if (sf > 0).any() else 0:.2f}s)")


def punteggiatura(events: list[SubtitleEvent]) -> None:
    """La durata dipende anche da **come finisce** la battuta?

    L'ipotesi viene dall'ascolto: una battuta che finisce con la virgola e' un
    pezzo di frase, il personaggio tira via, e il sottotitolo resta a schermo
    meno di quanto la sua lunghezza farebbe pensare. Se e' cosi', `D = a + b*n`
    la sovrastima sistematicamente — e sovrastimare la finestra significa
    comprimere troppo poco, cioe' sforare proprio dove c'e' un'altra battuta che
    arriva subito.

    Il confronto giusto non e' fra le durate — le battute con la virgola
    potrebbero essere semplicemente piu' corte di lettere — ma fra i **residui**
    rispetto alla retta. Un residuo mediano negativo su un gruppo dice: qui la
    retta sbaglia sempre nello stesso verso, e c'e' un pezzo di segnale che non
    sta usando.
    """
    usable = [e for e in events if e.duration is not None and letters(e.text) > 0]
    if len(usable) < 20:
        return
    n = np.array([letters(e.text) for e in usable], float)
    d = np.array([e.duration for e in usable], float)
    a, b = fit(n, d)
    res = d - (a + b * n)

    def classe(text: str) -> str:
        t = text.rstrip()
        if not t:
            return "altro"
        if t[-1] == ",":
            return "virgola"
        if t[-1] in ".!?":
            return "punto"
        if t.endswith("..") or t[-1] in "…":
            return "sospeso"
        return "altro"

    gruppi: dict[str, list[int]] = {}
    for i, e in enumerate(usable):
        gruppi.setdefault(classe(e.text), []).append(i)

    print("\n   come finisce      n   lettere p50   durata p50   residuo p50   residuo medio")
    for nome in ("virgola", "punto", "sospeso", "altro"):
        idx = gruppi.get(nome)
        if not idx or len(idx) < 5:
            continue
        print(
            f"   {nome:12} {len(idx):5d}   {np.median(n[idx]):9.0f}   {np.median(d[idx]):9.2f}s  "
            f"{np.median(res[idx]):+10.2f}s   {res[idx].mean():+11.2f}s"
        )
    virg = gruppi.get("virgola", [])
    punt = gruppi.get("punto", [])
    if len(virg) >= 5 and len(punt) >= 5:
        delta = float(np.median(res[virg]) - np.median(res[punt]))
        print(
            f"\n   la virgola vale {delta:+.2f}s di durata rispetto al punto, "
            f"a parita' di lunghezza."
        )
        if abs(delta) < 0.15:
            print("   Sotto i 150 ms non vale un termine in piu' nel modello: la")
            print("   dispersione dei residui e' molto piu' grande di questa differenza.")
        else:
            print("   Abbastanza da meritare un termine nel modello: una battuta che")
            print("   finisce col la virgola va prevista piu' corta, quindi compressa di piu'.")


def buckets(n: np.ndarray, d: np.ndarray, width: int = 10) -> None:
    """La durata mediana per fascia di lunghezza. Guardare prima di adattare."""
    print("\n   lunghezza    n   durata p50   p10..p90")
    edges = np.arange(0, int(n.max()) + width, width)
    for lo in edges:
        sel = (n >= lo) & (n < lo + width)
        if sel.sum() < 3:
            continue
        dd = d[sel]
        print(f"   {lo:3d}-{lo+width-1:3d}  {sel.sum():4d}   {np.median(dd):6.2f}s     "
              f"{np.percentile(dd,10):5.2f}..{np.percentile(dd,90):5.2f}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tools.bench_timing",
        description="Durata reale del sottotitolo contro numero di caratteri.",
    )
    ap.add_argument("input", help="JSONL di tools.replay --dump-reads, oppure un video")
    ap.add_argument("--profile", default=None, help="profilo del gioco")
    ap.add_argument("--set", action="append", dest="overrides", metavar="CHIAVE=VALORE")
    ap.add_argument(
        "--min-duration",
        type=float,
        default=0.6,
        help="sotto questa durata e' un frammento, non una battuta",
    )
    ap.add_argument("--min-letters", type=int, default=6, help="battute piu' corte si ignorano")
    ap.add_argument("--write", metavar="FILE", help="scrive i coefficienti nel profilo")
    args = ap.parse_args(argv)

    cfg = load_profile(args.profile, args.overrides) if args.profile else Config().apply(args.overrides)
    events = collect(args.input, cfg)
    usable = [e for e in events if e.duration is not None and letters(e.text) >= args.min_letters]
    if len(usable) < 10:
        print(f"troppe poche battute utilizzabili: {len(usable)}", file=sys.stderr)
        return 2

    n = np.array([letters(e.text) for e in usable], dtype=float)
    d = np.array([e.duration for e in usable], dtype=float)
    limits = (cfg.timing.rate_min, cfg.timing.rate_max)

    print(f"{len(events)} battute chiuse, {len(usable)} con almeno {args.min_letters} caratteri")
    describe("tutte", n, d, limits)

    keep = d >= args.min_duration
    print(f"\n{(~keep).sum()} battute sotto {args.min_duration:.1f}s: frammenti di una riaperta, "
          f"non battute corte")
    describe(f"senza i frammenti (>{args.min_duration:.1f}s)", n[keep], d[keep], limits)
    buckets(n[keep], d[keep])
    punteggiatura([e for e, k in zip(usable, keep) if k])
    a, b = fit(n[keep], d[keep])
    collisions([e for e, k in zip(usable, keep) if k], a, b)
    print(f"\ncoefficienti misurati:  predict_a = {a:.3f}   predict_b = {b:.4f}")
    print(f"coefficienti in config: predict_a = {cfg.timing.predict_a:.3f}   "
          f"predict_b = {cfg.timing.predict_b:.4f}")

    if args.write:
        import json

        path = Path(args.write)
        data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        data.setdefault("timing", {})["predict_a"] = round(a, 3)
        data["timing"]["predict_b"] = round(b, 4)
        data.setdefault("_calibrazione", {})["timing"] = {
            "battute": int(keep.sum()),
            "sorgente": Path(args.input).name,
            "residuo_mae": round(float(np.abs(d[keep] - (a + b * n[keep])).mean()), 3),
        }
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"-> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
